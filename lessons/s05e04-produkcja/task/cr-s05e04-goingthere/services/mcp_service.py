"""Unified client connecting to cr-mcp-workspace for session isolation and audit notes."""

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

    def __init__(self, workspace_url: str | None = None) -> None:
        self.workspace_url = workspace_url or config.MCP_WORKSPACE_URL
        self._tools_cache: dict[str, dict[str, Any]] = {}

    async def get_tools_for_session(self, session_id: str) -> list[Any]:
        """Retrieves and caches remote MCP tools for the given session ID."""
        if not self.workspace_url:
            logger.warning("MCP_WORKSPACE_URL is not set.")
            return []

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
            logger.warning(
                f"Failed to connect to remote cr-mcp-workspace at {self.workspace_url} ({e})."
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
        return {"result": str(extracted)}

    async def write_file(
        self,
        session_id: str,
        file_path: str,
        content: str,
        reasoning: str = "Persisting flight notes",
    ) -> dict[str, Any]:
        """Writes file directly to session-isolated GCS workspace via cr-mcp-workspace.
        Raises RuntimeError on failure to prevent silent local disk fallback.
        """
        clean_path = file_path.lstrip("/").replace("\\", "/")
        await self.get_tools_for_session(session_id)
        tool = self._get_tool(session_id, "write_file")

        if not tool:
            err_msg = (
                f"Required tool 'write_file' not available on cr-mcp-workspace for session {session_id}. "
                "Silent local container disk fallback is strictly prohibited."
            )
            logger.error(err_msg)
            raise RuntimeError(err_msg)

        try:
            res = await tool.ainvoke(
                {
                    "file_path": clean_path,
                    "content": content,
                    "reasoning": reasoning,
                }
            )
            parsed = self._parse_dict_response(res)
            logger.info(
                f"Successfully persisted {clean_path} to cr-mcp-workspace for session {session_id}"
            )
            return parsed
        except Exception as exc:
            err_msg = f"Failed to persist {clean_path} to cr-mcp-workspace: {exc}"
            logger.error(err_msg)
            raise RuntimeError(err_msg) from exc


mcp_service = MCPService()
