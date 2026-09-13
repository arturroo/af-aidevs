import json
import logging
import re
from typing import Any, Dict, List, Optional
from af_aidevs.clients.mcp import create_mcp_client, get_all_mcp_tools
import config

logger = logging.getLogger("services.mcp")


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

    def _get_tool(self, session_id: str, tool_name: str) -> Any:
        session_tools = self._tools_cache.get(session_id)
        if not session_tools:
            raise RuntimeError(
                f"MCP tools not initialized for session {session_id}. Call get_tools_for_session first."
            )

        if tool_name in session_tools:
            return session_tools[tool_name]

        for k, v in session_tools.items():
            if k.endswith(tool_name):
                return v

        raise ValueError(
            f"MCP tool '{tool_name}' not found. Available: {list(session_tools.keys())}"
        )

    @staticmethod
    def _extract_raw(result: Any) -> Any:
        """Extracts underlying content or dict from LangChain tool output."""
        if hasattr(result, "content"):
            return MCPService._extract_raw(result.content)
        if isinstance(result, list) and len(result) == 1:
            return MCPService._extract_raw(result[0])
        if isinstance(result, dict) and "text" in result:
            return result["text"]
        return result

    @classmethod
    def _parse_dict_response(cls, result: Any) -> Dict[str, Any]:
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

    async def fetch_web_resource(
        self, session_id: str, url: str, output_path: str = "sensors.zip"
    ) -> Dict[str, Any]:
        """Downloads external resource directly to the session workspace via cr-mcp-web-gateway."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)
        tool = self._get_tool(session_id, "fetch_web_resource")
        raw_result = await tool.ainvoke({"url": url, "output_path": output_path})
        return self._parse_dict_response(raw_result)

    async def read_binary_file(
        self, session_id: str, file_path: str, reasoning: str
    ) -> Dict[str, Any]:
        """Reads a binary file from the workspace via cr-mcp-workspace and returns Base64 & SHA-256."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)
        tool = self._get_tool(session_id, "read_binary_file")
        raw_result = await tool.ainvoke(
            {"file_path": file_path, "reasoning": reasoning}
        )
        return self._parse_dict_response(raw_result)

    async def write_file(
        self, session_id: str, file_path: str, content: str, reasoning: str
    ) -> Dict[str, Any]:
        """Writes text content to workspace file (e.g. run_notes.txt) via cr-mcp-workspace."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)
        tool = self._get_tool(session_id, "write_file")
        raw_result = await tool.ainvoke(
            {"file_path": file_path, "content": content, "reasoning": reasoning}
        )
        return self._parse_dict_response(raw_result)

    async def post_web_resource(
        self, session_id: str, url: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatches external HTTP POST request via cr-mcp-web-gateway."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)
        tool = self._get_tool(session_id, "post_web_resource")
        try:
            raw_result = await tool.ainvoke({"url": url, "payload": payload})
            return self._parse_dict_response(raw_result)
        except Exception as e:
            err_str = str(e)
            logger.warning(f"post_web_resource caught exception: {err_str}")
            match = re.search(r"(\{.*\})", err_str, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    pass
            return {"status": "error", "error": err_str}
