"""Workspace staging client connecting directly to cr-mcp-workspace with local fallback."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from af_aidevs.clients.mcp import get_all_mcp_tools

import config
from schemas import FilesystemFile

logger = logging.getLogger("services.mcp")


class MCPService:
    """Manages workspace operations directly via cr-mcp-workspace or local fallback."""

    def __init__(
        self,
        workspace_url: str | None = None,
        local_base: Path | None = None,
    ):
        self.workspace_url = workspace_url or config.MCP_WORKSPACE_URL
        self.local_base = local_base or config.LOCAL_WORKSPACE_DIR
        self._tools_cache: dict[str, dict[str, Any]] = {}
        self.local_base.mkdir(parents=True, exist_ok=True)

    async def get_tools_for_session(self, session_id: str) -> list[Any]:
        """Retrieves and caches remote MCP tools for the given session ID."""
        try:
            tools = await get_all_mcp_tools(
                session_id=session_id,
                workspace_url=self.workspace_url,
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
        if isinstance(result, list) and len(result) == 1:
            return MCPService._extract_raw(result[0])
        if isinstance(result, dict) and "text" in result:
            return result["text"]
        return result

    @classmethod
    def _parse_dict_response(cls, result: Any) -> dict[str, Any]:
        raw = cls._extract_raw(result)
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            text = raw.strip()
            try:
                return json.loads(text)
            except Exception:
                match = re.search(r"(\{.*\})", text, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group(1))
                    except Exception:
                        pass
            return {"raw_output": text}
        return {"raw_output": str(raw)}

    def _resolve_local_path(self, session_id: str, rel_path: str) -> Path:
        clean = rel_path.lstrip("/\\")
        if clean.startswith("workspace/"):
            clean = clean[len("workspace/") :]
        elif clean.startswith("workspace\\"):
            clean = clean[len("workspace\\") :]
        return self.local_base / session_id / clean

    async def write_file(
        self, session_id: str, file_path: str, content: str, reasoning: str = ""
    ) -> dict[str, Any]:
        """Writes text content to workspace file via cr-mcp-workspace with local fallback."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)

        clean_path = file_path.lstrip("/")
        tool = self._get_tool(session_id, "write_file")
        if tool:
            try:
                raw_result = await tool.ainvoke(
                    {
                        "file_path": clean_path,
                        "content": content,
                        "reasoning": reasoning,
                    }
                )
                logger.info(f"Wrote {clean_path} via cr-mcp-workspace")
                return self._parse_dict_response(raw_result)
            except Exception as e:
                logger.warning(f"MCP write_file failed ({e}), using local fallback.")

        # Local fallback
        target = self._resolve_local_path(session_id, clean_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {
            "status": "success",
            "file_path": str(target),
            "bytes_written": len(content),
        }

    async def read_file(
        self, session_id: str, file_path: str, reasoning: str = ""
    ) -> str:
        """Reads a file from cr-mcp-workspace with local fallback."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)

        clean_path = file_path.lstrip("/")
        tool = self._get_tool(session_id, "read_file")
        if tool:
            try:
                raw_result = await tool.ainvoke(
                    {"file_path": clean_path, "reasoning": reasoning}
                )
                parsed = self._parse_dict_response(raw_result)
                if isinstance(parsed, dict) and "content" in parsed:
                    return str(parsed["content"])
                if isinstance(parsed, dict) and "text" in parsed:
                    return str(parsed["text"])
                raw_text = self._extract_raw(raw_result)
                return str(raw_text) if raw_text is not None else ""
            except Exception as e:
                logger.warning(f"MCP read_file failed ({e}), using local fallback.")

        target = self._resolve_local_path(session_id, clean_path)
        if target.exists() and target.is_file():
            return target.read_text(encoding="utf-8")
        return ""

    async def list_files(
        self, session_id: str, path: str = ".", reasoning: str = ""
    ) -> list[str]:
        """Lists file paths under given path from cr-mcp-workspace."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)

        clean_path = path.lstrip("/") if path not in (".", "/") else "."
        tool = self._get_tool(session_id, "list_files")
        if tool:
            try:
                raw_result = await tool.ainvoke(
                    {"path": clean_path, "reasoning": reasoning}
                )
                parsed = self._parse_dict_response(raw_result)
                file_list: list[str] = []
                # cr-mcp-workspace returns {"status": "success", "files": [...]}
                if isinstance(parsed, dict) and "files" in parsed:
                    for item in parsed["files"]:
                        name = item.get("name") if isinstance(item, dict) else str(item)
                        file_type = (
                            item.get("type", "file")
                            if isinstance(item, dict)
                            else "file"
                        )
                        if file_type == "file" and name:
                            file_list.append(name)
                return file_list
            except Exception as e:
                logger.warning(f"MCP list_files failed ({e}), using local fallback.")

        target = self._resolve_local_path(session_id, clean_path)
        if not target.exists():
            return []
        return [p.name for p in target.iterdir() if p.is_file()]

    async def list_all_workspace_files(self, session_id: str) -> list[FilesystemFile]:
        """Lists and fetches content of all staged virtual filesystem files across /miasta, /osoby, /towary."""
        results: list[FilesystemFile] = []
        for category in ["miasta", "osoby", "towary"]:
            filenames = await self.list_files(session_id=session_id, path=category)
            for fname in filenames:
                vpath = f"/{category}/{fname}"
                content = await self.read_file(session_id=session_id, file_path=vpath)
                results.append(FilesystemFile(path=vpath, content=content))
        return results
