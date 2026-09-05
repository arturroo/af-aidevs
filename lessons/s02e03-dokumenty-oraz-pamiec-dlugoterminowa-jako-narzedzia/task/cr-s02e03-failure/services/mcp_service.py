import os
import json
import logging
from typing import Optional, Dict, Any, List
from af_aidevs.clients.mcp import get_all_mcp_tools, create_mcp_client
import config

logger = logging.getLogger("services.mcp")


class MCPService:
    """Unified client service orchestrating interactions with cr-mcp-web-gateway and cr-mcp-workspace."""

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
        # Store by normalized name for fast lookup
        tool_map: Dict[str, Any] = {}
        for t in tools:
            # Handle possible server prefixes e.g. web_fetch_web_resource or fetch_web_resource
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
            raise RuntimeError(f"MCP tools not initialized for session {session_id}. Call get_tools_for_session first.")

        if tool_name in session_tools:
            return session_tools[tool_name]

        for k, v in session_tools.items():
            if k.endswith(tool_name):
                return v

        raise ValueError(f"MCP tool '{tool_name}' not found. Available: {list(session_tools.keys())}")

    @staticmethod
    def _extract_text_content(result: Any) -> str:
        """Robustly unwraps raw string content from LangChain / MCP tool return formats."""
        if hasattr(result, "content"):
            return MCPService._extract_text_content(result.content)

        if isinstance(result, list):
            texts = []
            for item in result:
                if isinstance(item, dict):
                    if "text" in item:
                        texts.append(str(item["text"]))
                    elif "content" in item:
                        texts.append(str(item["content"]))
                    else:
                        texts.append(json.dumps(item))
                elif hasattr(item, "text"):
                    texts.append(str(item.text))
                else:
                    texts.append(str(item))
            joined = "\n".join(texts)
            return MCPService._extract_text_content(joined)

        if isinstance(result, dict):
            if "content" in result and result["content"] is not None:
                return MCPService._extract_text_content(result["content"])
            if "text" in result and result["text"] is not None:
                return MCPService._extract_text_content(result["text"])
            return json.dumps(result)

        if isinstance(result, str):
            clean = result.strip()
            if clean.startswith("{") and clean.endswith("}"):
                try:
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict):
                        if "content" in parsed and parsed["content"] is not None:
                            return MCPService._extract_text_content(parsed["content"])
                        if "text" in parsed and parsed["text"] is not None:
                            return MCPService._extract_text_content(parsed["text"])
                except Exception:
                    pass
            return result

        return str(result)

    async def fetch_web_resource(self, session_id: str, url: str, output_path: str = "failure.log") -> str:
        """
        Uses cr-mcp-web-gateway to download an external file directly into the session workspace.
        """
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)
        tool = self._get_tool(session_id, "fetch_web_resource")
        result = await tool.ainvoke({"url": url, "output_path": output_path})
        return self._extract_text_content(result)

    async def post_web_resource(self, session_id: str, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Uses cr-mcp-web-gateway to send an external POST request and receive the JSON response.
        """
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)
        tool = self._get_tool(session_id, "post_web_resource")
        try:
            raw_result = await tool.ainvoke({"url": url, "payload": payload})
            text_result = self._extract_text_content(raw_result)
            try:
                return json.loads(text_result)
            except Exception:
                import re
                json_match = re.search(r"(\{.*\})", text_result, re.DOTALL)
                if json_match:
                    try:
                        return json.loads(json_match.group(1))
                    except Exception:
                        pass
                return {"raw_output": text_result}
        except Exception as e:
            err_str = str(e)
            logger.warning(f"post_web_resource caught response: {err_str}")
            import re
            json_match = re.search(r"(\{.*\})", err_str, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(1))
                    if isinstance(parsed, dict) and ("code" in parsed or "message" in parsed):
                        return parsed
                except Exception:
                    pass
            raise e

    async def read_file(self, session_id: str, file_path: str = "failure.log") -> str:
        """
        Reads a file from the session workspace via cr-mcp-workspace.
        """
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)
        tool = self._get_tool(session_id, "read_file")
        result = await tool.ainvoke({
            "reasoning": f"Reading file '{file_path}' from session workspace",
            "file_path": file_path,
        })
        return self._extract_text_content(result)

    async def write_file(self, session_id: str, file_path: str, content: str) -> str:
        """
        Writes content to a file in the session workspace via cr-mcp-workspace.
        """
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)
        tool = self._get_tool(session_id, "write_file")
        result = await tool.ainvoke({
            "reasoning": f"Writing execution summary to '{file_path}' in session workspace",
            "file_path": file_path,
            "content": content,
        })
        return self._extract_text_content(result)

    async def grep(
        self,
        session_id: str,
        pattern: str,
        file_path: str = "failure.log",
        flags: Optional[List[str]] = None,
    ) -> str:
        """
        Executes a targeted grep search in the session workspace via cr-mcp-workspace.
        """
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)
        tool = self._get_tool(session_id, "grep")
        result = await tool.ainvoke({
            "reasoning": f"Searching for '{pattern}' in '{file_path}'",
            "pattern": pattern,
            "file_path": file_path,
            "flags": flags or ["-i"],
        })
        return self._extract_text_content(result)
