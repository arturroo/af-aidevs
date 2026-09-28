"""Unified client connecting to cr-mcp-workspace via af_aidevs."""

import json
import logging
import re
from typing import Any

from af_aidevs.auth.oidc import GoogleOIDCAuth
from langchain_mcp_adapters.client import MultiServerMCPClient

from config import config

logger = logging.getLogger("services.mcp")


class MCPService:
    """Unified client connecting to cr-mcp-workspace via af_aidevs."""

    def __init__(self, workspace_url: str | None = None):
        self.workspace_url = workspace_url or config.MCP_WORKSPACE_URL
        self._tools_cache: dict[str, dict[str, Any]] = {}

    async def get_tools_for_session(self, session_id: str) -> list[Any]:
        """Retrieves and caches remote MCP tools for the given session ID."""
        try:
            client = MultiServerMCPClient(
                {
                    "workspace": {
                        "transport": "http",
                        "url": f"{self.workspace_url}/mcp",
                        "headers": {"X-Session-ID": session_id},
                        "auth": GoogleOIDCAuth(self.workspace_url),
                    }
                }
            )
            tools = await client.get_tools()
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
            logger.warning(f"Failed to connect to remote cr-mcp-workspace ({e}).")
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
            return {"raw_output": text}
        return {"raw_output": str(raw)}

    async def write_file(
        self,
        session_id: str,
        file_path: str,
        content: str,
        reasoning: str = "Persisting session run notes",
    ) -> dict[str, Any]:
        """Writes text content to workspace file via cr-mcp-workspace."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)

        tool = self._get_tool(session_id, "write_file")
        if tool:
            try:
                raw_result = await tool.ainvoke(
                    {"file_path": file_path, "content": content, "reasoning": reasoning}
                )
                parsed = self._parse_dict_response(raw_result)
                logger.info(
                    f"Persisted {file_path} to cr-mcp-workspace for session {session_id}: {parsed}"
                )
                return parsed
            except Exception as e:
                logger.warning(f"cr-mcp-workspace write_file failed: {e}")
                return {"status": "error", "message": str(e)}

        logger.warning(
            f"Tool write_file not found in cr-mcp-workspace for session {session_id}"
        )
        return {"status": "error", "message": "tool write_file not available"}

    async def read_file(
        self, session_id: str, file_path: str, reasoning: str = "Reading workspace file"
    ) -> dict[str, Any]:
        """Reads a text file from workspace via cr-mcp-workspace."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)

        tool = self._get_tool(session_id, "read_file")
        if tool:
            try:
                raw_result = await tool.ainvoke(
                    {"file_path": file_path, "reasoning": reasoning}
                )
                return self._parse_dict_response(raw_result)
            except Exception as e:
                logger.warning(f"cr-mcp-workspace read_file failed: {e}")
                return {"status": "error", "message": str(e)}

        return {"status": "not_found", "file_path": file_path, "content": ""}


mcp_service = MCPService()
