import asyncio
import base64
from contextlib import contextmanager
import gzip
import json
import logging
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

import sqlite_vec
from af_aidevs.clients.mcp import get_all_mcp_tools
from langsmith import traceable

import config

logger = logging.getLogger(__name__)


def extract_content_base64(raw_res: Any) -> str:
    """Robustly extracts content_base64 string from various MCP / LangChain response formats."""
    curr = raw_res
    if hasattr(curr, "content"):
        curr = curr.content

    if isinstance(curr, list) and curr:
        for item in curr:
            try:
                res = extract_content_base64(item)
                if res:
                    return res
            except Exception:
                continue
        curr = curr[0]

    if isinstance(curr, dict):
        if "content_base64" in curr and isinstance(curr["content_base64"], str):
            return curr["content_base64"]
        if "text" in curr:
            return extract_content_base64(curr["text"])
        if "result" in curr:
            return extract_content_base64(curr["result"])

    if isinstance(curr, str):
        curr_str = curr.strip()
        if curr_str.startswith("{") or curr_str.startswith("["):
            try:
                parsed = json.loads(curr_str)
                return extract_content_base64(parsed)
            except Exception:
                pass

        match = re.search(r'["\']content_base64["\']\s*:\s*["\']([A-Za-z0-9+/=]+)["\']', curr_str)
        if match:
            return match.group(1)

        try:
            decoded_header = base64.b64decode(curr_str[:64])
            if b"SQLite format 3" in decoded_header or len(curr_str) > 1000:
                return curr_str
        except Exception:
            pass

    raise ValueError(
        f"Could not extract content_base64 from cr-mcp-workspace response (type: {type(raw_res).__name__})"
    )


def mask_binary_output(output: Any) -> Any:
    """Mask heavy base64 strings in LangSmith / Langfuse traces, preserving metadata."""
    if isinstance(output, dict):
        sanitized = dict(output)
        for key in ("content_base64", "base64", "data"):
            if key in sanitized and isinstance(sanitized[key], str) and len(sanitized[key]) > 200:
                b64_len = len(sanitized[key])
                est_bytes = (b64_len * 3) // 4
                sanitized[key] = f"<REDACTED_BASE64: {b64_len} chars, ~{est_bytes} bytes>"
        return sanitized
    if hasattr(output, "content") and isinstance(output.content, str) and len(output.content) > 500:
        return f"<REDACTED_OUTPUT: {len(output.content)} chars>"
    return output


@traceable(name="read_binary_file", run_type="tool", process_outputs=mask_binary_output)
async def invoke_mcp_tool_with_masked_output(tool, tool_input: dict) -> Any:
    """Invoke an MCP tool while masking large Base64 outputs in LangSmith/Langfuse traces."""
    # Execute underlying tool with callbacks disabled to avoid unmasked raw dump,
    # letting @traceable register the clean, sanitized trace in LangSmith/Langfuse.
    return await tool.ainvoke(tool_input, config={"callbacks": []})


class DatabaseService:
    """Manages immutable SQLite inventory database connections and queries."""

    _instance: Optional["DatabaseService"] = None

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.INVENTORY_DB_PATH
        self._items_cache: Optional[List[Dict[str, str]]] = None

    @classmethod
    def get_instance(cls, db_path: Optional[Path] = None) -> "DatabaseService":
        if cls._instance is None:
            cls._instance = DatabaseService(db_path)
        return cls._instance

    def ensure_db_exists(self) -> None:
        """Verify DB exists locally, otherwise download via cr-mcp-workspace."""
        if not self.db_path.exists():
            logger.warning(
                "Local inventory.db not found at %s. Downloading via cr-mcp-workspace...",
                self.db_path,
            )
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(asyncio.run, self.download_db_from_workspace()).result()
            else:
                asyncio.run(self.download_db_from_workspace())

    async def download_db_from_workspace(self, session_id: str = "s03e04_db_init") -> None:
        """Download inventory.db from cr-mcp-workspace using read_binary_file (Zero-Trust Shared Layer)."""
        try:
            logger.info(
                "Connecting to cr-mcp-workspace at %s to fetch inventory.db...",
                config.MCP_WORKSPACE_URL,
            )
            tools = await get_all_mcp_tools(
                session_id=session_id,
                workspace_url=config.MCP_WORKSPACE_URL,
                web_url=config.MCP_WEB_GATEWAY_URL,
            )
            tool = next(
                (t for t in tools if t.name in ("read_binary_file", "workspace_read_binary_file")),
                None,
            )
            if not tool:
                raise RuntimeError(
                    f"Tool read_binary_file not found on cr-mcp-workspace. Available tools: {[t.name for t in tools]}"
                )

            # Attempt to fetch compressed inventory.db.gz first to save network egress, falling back to uncompressed
            db_candidates = ["inventory.db.gz", "inventory.db"]
            target_filename = "inventory.db.gz"
            raw_res = None
            last_err = None

            for cand in db_candidates:
                try:
                    logger.info("Attempting to fetch %s from cr-mcp-workspace...", cand)
                    raw_res = await invoke_mcp_tool_with_masked_output(
                        tool,
                        {
                            "file_path": cand,
                            "reasoning": f"Fetch {cand} from shared layer into local container /tmp cache",
                        },
                    )
                    if raw_res:
                        target_filename = cand
                        break
                except Exception as ex:
                    last_err = ex
                    logger.warning("Could not fetch %s from cr-mcp-workspace: %s", cand, ex)

            if not raw_res:
                raise RuntimeError(f"Failed to fetch inventory database from cr-mcp-workspace: {last_err}")

            content_base64 = extract_content_base64(raw_res)
            raw_bytes = base64.b64decode(content_base64)

            # Auto-decompress if gzip format is detected (.gz extension or 0x1f 0x8b magic header)
            if target_filename.endswith(".gz") or raw_bytes[:2] == b"\x1f\x8b":
                logger.info(
                    "Detected gzip compressed database (%d bytes). Decompressing...",
                    len(raw_bytes),
                )
                t0 = time.perf_counter()
                decompressed_bytes = gzip.decompress(raw_bytes)
                dt = time.perf_counter() - t0
                logger.info(
                    "Successfully decompressed database in %.2f ms (wire compressed: %d bytes -> sqlite: %d bytes)",
                    dt * 1000,
                    len(raw_bytes),
                    len(decompressed_bytes),
                )
                raw_bytes = decompressed_bytes

            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path.write_bytes(raw_bytes)
            logger.info(
                "Successfully saved uncompressed database to %s (%d bytes)",
                self.db_path,
                len(raw_bytes),
            )
            self._items_cache = None
        except Exception as e:
            logger.error("Failed to download database from cr-mcp-workspace: %s", e)
            raise

    @contextmanager
    def get_connection(self):
        """Open read-only connection with sqlite-vec extension loaded and automatically close it."""
        self.ensure_db_exists()
        # Open in immutable read-only mode via URI
        uri_path = f"file:{self.db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri_path, uri=True)
        conn.row_factory = sqlite3.Row

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        try:
            yield conn
        finally:
            conn.close()

    def get_all_items(self) -> List[Dict[str, str]]:
        """Get all items from catalog (cached in memory for lexical search)."""
        if self._items_cache is not None:
            return self._items_cache

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT code, name FROM items;")
            rows = cursor.fetchall()
            self._items_cache = [{"code": r["code"], "name": r["name"]} for r in rows]
            return self._items_cache

    def get_stocking_cities_for_items(self, item_codes: List[str]) -> Dict[str, List[str]]:
        """Get list of cities stocking each given item code."""
        if not item_codes:
            return {}

        placeholders = ",".join("?" for _ in item_codes)
        query = f"""
            SELECT cn.itemCode, c.name AS cityName
            FROM connections cn
            JOIN cities c ON cn.cityCode = c.code
            WHERE cn.itemCode IN ({placeholders})
            ORDER BY c.name ASC;
        """
        result: Dict[str, List[str]] = {code: [] for code in item_codes}
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, item_codes)
            for row in cursor.fetchall():
                result[row["itemCode"]].append(row["cityName"])
        return result

    def find_cities_stocking_all_items(self, item_codes: List[str]) -> List[Dict[str, str]]:
        """Find cities that stock ALL specified items simultaneously via parametric SQL."""
        if not item_codes:
            return []

        # Deduplicate codes while preserving order
        unique_codes = list(dict.fromkeys(item_codes))
        count = len(unique_codes)

        placeholders = ",".join("?" for _ in unique_codes)
        params = list(unique_codes) + [count]

        query = f"""
            SELECT c.name, c.code
            FROM cities c
            JOIN connections cn ON c.code = cn.cityCode
            WHERE cn.itemCode IN ({placeholders})
            GROUP BY c.code, c.name
            HAVING COUNT(DISTINCT cn.itemCode) = ?
            ORDER BY c.name ASC;
        """

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [{"name": r["name"], "code": r["code"]} for r in cursor.fetchall()]
