import base64
import json
import logging
import re
from pathlib import Path
from typing import Any

from af_aidevs.clients.mcp import get_all_mcp_tools

import config

logger = logging.getLogger("services.mcp")


class MCPService:
    """Unified client connecting to cr-mcp-workspace with transparent local /tmp caching and APPEND_ONLY mode."""

    def __init__(
        self,
        workspace_url: str | None = None,
        web_url: str | None = None,
        cache_base: Path | None = None,
    ):
        self.workspace_url = workspace_url or config.MCP_WORKSPACE_URL
        self.web_url = web_url or config.MCP_WEB_GATEWAY_URL
        self.cache_base = cache_base or config.LOCAL_CACHE_DIR
        self._tools_cache: dict[str, dict[str, Any]] = {}
        self.cache_base.mkdir(parents=True, exist_ok=True)

    def _get_session_cache_dir(self, session_id: str) -> Path:
        sdir = self.cache_base / session_id
        sdir.mkdir(parents=True, exist_ok=True)
        return sdir

    async def get_tools_for_session(self, session_id: str) -> list[Any]:
        """Retrieves and caches remote MCP tools for the given session ID."""
        try:
            tools = await get_all_mcp_tools(
                session_id=session_id,
                workspace_url=self.workspace_url,
                web_url=self.web_url,
            )
            tool_map: dict[str, Any] = {}
            for t in tools:
                name = t.name
                tool_map[name] = t
                if "_" in name:
                    short_name = name.split("_", 1)[1]
                    tool_map.setdefault(short_name, t)
            self._tools_cache[session_id] = tool_map
            return tools
        except Exception as e:
            logger.warning(
                f"Failed to connect to remote MCP servers ({e}). Using local workspace fallback."
            )
            self._tools_cache[session_id] = {}
            return []

    def _get_tool(self, session_id: str, tool_name: str) -> Any | None:
        session_tools = self._tools_cache.get(session_id, {})
        if tool_name in session_tools:
            return session_tools[tool_name]
        for k, v in session_tools.items():
            if k.endswith(tool_name):
                return v
        return None

    @staticmethod
    def _extract_raw(result: Any) -> Any:
        if hasattr(result, "content"):
            return MCPService._extract_raw(result.content)
        if isinstance(result, list) and len(result) > 0:
            return MCPService._extract_raw(result[0])
        return result

    @staticmethod
    def _parse_dict_response(raw: Any) -> dict[str, Any]:
        extracted = MCPService._extract_raw(raw)
        if isinstance(extracted, dict):
            if "text" in extracted and isinstance(extracted["text"], str):
                try:
                    inner = json.loads(extracted["text"])
                    if isinstance(inner, dict):
                        return inner
                except Exception:
                    pass
            return extracted
        if isinstance(extracted, str):
            text = extracted.strip()
            try:
                return json.loads(text)
            except Exception:
                match = re.search(r"(\{.*\})", text, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group(1))
                    except Exception:
                        pass
            return {"raw_text": text}
        return {"result": str(extracted)}

    def get_gcs_uri(self, session_id: str, file_path: str) -> str:
        """Returns the canonical GCS URI for an artifact in the session workspace."""
        clean_path = file_path.lstrip("/").replace("\\", "/")
        return f"gs://{config.GCS_WORKSPACE_BUCKET}/sa-cr-mcp-workspace/{session_id}/{clean_path}"

    async def write_file(
        self, session_id: str, file_path: str, content: str | bytes
    ) -> dict[str, Any]:
        """Write-Through caching: saves to remote cr-mcp-workspace and immediately caches locally in /tmp."""
        clean_path = file_path.lstrip("/").replace("\\", "/")
        local_cache_path = self._get_session_cache_dir(session_id) / clean_path
        local_cache_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, str):
            local_cache_path.write_text(content, encoding="utf-8")
        else:
            local_cache_path.write_bytes(content)

        tool = self._get_tool(session_id, "write_file")
        if tool:
            try:
                # If bytes, base64 encode or convert to str if needed
                text_content = (
                    content
                    if isinstance(content, str)
                    else base64.b64encode(content).decode("ascii")
                )
                res = await tool.ainvoke(
                    {
                        "file_path": clean_path,
                        "content": text_content,
                        "reasoning": f"Staging {clean_path} in session {session_id}",
                    }
                )
                return self._parse_dict_response(res)
            except Exception as e:
                logger.warning(
                    f"Remote MCP write_file failed ({e}). File cached locally at {local_cache_path}"
                )

        return {"status": "success", "file_path": clean_path, "cached": True}

    async def read_file(self, session_id: str, file_path: str) -> str:
        """Read-Through caching: serves from local /tmp cache if present, otherwise fetches from remote MCP."""
        clean_path = file_path.lstrip("/").replace("\\", "/")
        local_cache_path = self._get_session_cache_dir(session_id) / clean_path

        if local_cache_path.exists() and local_cache_path.is_file():
            return local_cache_path.read_text(encoding="utf-8", errors="replace")

        tool = self._get_tool(session_id, "read_file")
        if tool:
            try:
                res = await tool.ainvoke(
                    {
                        "file_path": clean_path,
                        "reasoning": f"Reading {clean_path} for session {session_id}",
                    }
                )
                parsed = self._parse_dict_response(res)
                content = (
                    parsed.get("content")
                    or parsed.get("text")
                    or parsed.get("raw_text")
                    or ""
                )
                local_cache_path.parent.mkdir(parents=True, exist_ok=True)
                local_cache_path.write_text(content, encoding="utf-8")
                return content
            except Exception as e:
                logger.warning(f"Remote MCP read_file failed for {clean_path}: {e}")

        # Local workspace fallback
        local_ws_path = config.LOCAL_WORKSPACE_DIR / clean_path
        if local_ws_path.exists() and local_ws_path.is_file():
            return local_ws_path.read_text(encoding="utf-8", errors="replace")

        raise FileNotFoundError(f"File not found: {clean_path}")

    async def read_binary_file(self, session_id: str, file_path: str) -> bytes:
        """Reads binary file serving from local cache if present, otherwise fetches remotely."""
        clean_path = file_path.lstrip("/").replace("\\", "/")
        local_cache_path = self._get_session_cache_dir(session_id) / clean_path

        if local_cache_path.exists() and local_cache_path.is_file():
            return local_cache_path.read_bytes()

        tool = self._get_tool(session_id, "read_binary_file") or self._get_tool(
            session_id, "read_file"
        )
        if tool:
            try:
                res = await tool.ainvoke(
                    {
                        "file_path": clean_path,
                        "reasoning": f"Reading binary {clean_path} for session {session_id}",
                    }
                )
                parsed = self._parse_dict_response(res)
                content_b64 = (
                    parsed.get("content_base64")
                    or parsed.get("attachment")
                    or parsed.get("content")
                    or ""
                )
                binary_data = base64.b64decode(content_b64)
                local_cache_path.parent.mkdir(parents=True, exist_ok=True)
                local_cache_path.write_bytes(binary_data)
                return binary_data
            except Exception as e:
                logger.warning(
                    f"Remote MCP read_binary_file failed for {clean_path}: {e}"
                )

        local_ws_path = config.LOCAL_WORKSPACE_DIR / clean_path
        if local_ws_path.exists() and local_ws_path.is_file():
            return local_ws_path.read_bytes()

        raise FileNotFoundError(f"Binary file not found: {clean_path}")

    async def list_files(self, session_id: str, directory: str = "") -> list[str]:
        """Lists files in the session workspace."""
        clean_dir = directory.lstrip("/").replace("\\", "/")
        tool = self._get_tool(session_id, "list_files")
        if tool:
            try:
                res = await tool.ainvoke(
                    {
                        "path": clean_dir or ".",
                        "reasoning": f"Listing files for session {session_id}",
                    }
                )
                parsed = self._parse_dict_response(res)
                files = parsed.get("files") or parsed.get("entries") or []
                if isinstance(files, list):
                    clean_prefix = clean_dir.strip("/")
                    result_paths = []
                    for f in files:
                        name = (
                            f.get("name") or f.get("path")
                            if isinstance(f, dict)
                            else str(f)
                        )
                        if not name:
                            continue
                        full_path = (
                            f"{clean_prefix}/{name}".strip("/")
                            if clean_prefix and clean_prefix != "."
                            else name
                        )
                        result_paths.append(full_path)
                    return result_paths
            except Exception as e:
                logger.warning(f"Remote MCP list_files failed: {e}")

        # Fallback to local session cache
        sdir = self._get_session_cache_dir(session_id)
        if sdir.exists():
            target_dir = sdir / clean_dir if clean_dir and clean_dir != "." else sdir
            if target_dir.exists():
                return [
                    p.relative_to(sdir).as_posix()
                    for p in target_dir.rglob("*")
                    if p.is_file()
                ]
        return []
