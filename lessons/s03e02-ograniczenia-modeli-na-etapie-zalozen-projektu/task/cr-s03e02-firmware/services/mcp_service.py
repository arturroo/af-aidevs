import json
import logging
import re
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger("services.mcp")

try:
    from af_aidevs.clients.mcp import get_all_mcp_tools
except ImportError:
    get_all_mcp_tools = None

import config


class MCPService:
    """Unified client orchestrating interactions with cr-mcp-web-gateway and cr-mcp-workspace."""

    def __init__(
        self,
        workspace_url: Optional[str] = None,
        web_url: Optional[str] = None,
    ):
        self.workspace_url = workspace_url or config.MCP_WORKSPACE_URL
        self.web_url = web_url or config.MCP_WEB_GATEWAY_URL
        self._tools_cache: Dict[str, Dict[str, Any]] = {}

    async def get_tools_for_session(self, session_id: str) -> List[Any]:
        """Retrieves and caches all remote MCP tools from cr-mcp-web-gateway and cr-mcp-workspace."""
        if get_all_mcp_tools is None:
            return []
        try:
            tools = await get_all_mcp_tools(
                session_id=session_id,
                workspace_url=self.workspace_url,
                web_url=self.web_url,
            )
            tool_map: Dict[str, Any] = {}
            for t in tools:
                name = t.name
                tool_map[name] = t
                if "_" in name:
                    short_name = name.split("_", 1)[1]
                    tool_map.setdefault(short_name, t)
            self._tools_cache[session_id] = tool_map
            return tools
        except Exception as e:
            logger.warning(f"Could not initialize remote MCP tools: {e}")
            return []

    async def write_file(
        self, session_id: str, file_path: str, content: str, reasoning: str = "Writing run notes summary"
    ) -> Dict[str, Any]:
        """Writes text content to workspace file (e.g. run_notes.txt) via cr-mcp-workspace with local fallback."""
        try:
            if session_id not in self._tools_cache:
                await self.get_tools_for_session(session_id)
            session_tools = self._tools_cache.get(session_id, {})
            tool = session_tools.get("write_file") or next((v for k, v in session_tools.items() if k.endswith("write_file")), None)
            if tool:
                raw_result = await tool.ainvoke(
                    {"file_path": file_path, "content": content, "reasoning": reasoning}
                )
                return {"status": "success", "result": str(raw_result)}
        except Exception as e:
            logger.warning(f"MCP write_file failed: {e}. Writing locally.")

        # Local fallback
        try:
            local_path = Path(__file__).parent.parent / file_path
            local_path.write_text(content, encoding="utf-8")
            return {"status": "success", "local_path": str(local_path)}
        except Exception as err:
            logger.error(f"Local file write failed: {err}")
            return {"status": "error", "error": str(err)}
