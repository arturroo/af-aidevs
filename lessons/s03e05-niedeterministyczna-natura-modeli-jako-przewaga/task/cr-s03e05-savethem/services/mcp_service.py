import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential
from af_aidevs.clients.mcp import get_all_mcp_tools
import config

logger = logging.getLogger("services.mcp")


class CentralaRateLimitError(Exception):
    """Raised when Centrala returns rate limit code -9999 or 429 throttle signal."""
    pass


class MCPService:
    """Unified client connecting to cr-mcp-web-gateway and cr-mcp-workspace."""

    def __init__(
        self,
        workspace_url: Optional[str] = None,
        web_url: Optional[str] = None,
    ):
        self.workspace_url = workspace_url or config.MCP_WORKSPACE_URL
        self.web_url = web_url or config.MCP_WEB_GATEWAY_URL
        self._tools_cache: Dict[str, Dict[str, Any]] = {}
        self._local_workspace_base = Path("/tmp/af_aidevs_workspace")

    async def get_tools_for_session(self, session_id: str) -> List[Any]:
        """Retrieves and caches remote MCP tools for the given session ID."""
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
            logger.warning(
                f"Failed to connect to remote MCP servers ({e}). Using local fallback."
            )
            self._tools_cache[session_id] = {}
            return []

    def _get_tool(self, session_id: str, tool_name: str) -> Optional[Any]:
        session_tools = self._tools_cache.get(session_id, {})
        if tool_name in session_tools:
            return session_tools[tool_name]
        for k, v in session_tools.items():
            if k.endswith(tool_name):
                return v
        return None

    @staticmethod
    def _extract_raw(result: Any) -> Any:
        """Extracts underlying content or dict from LangChain/MCP tool output."""
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

    @retry(
        retry=retry_if_exception_type((CentralaRateLimitError, httpx.HTTPStatusError, httpx.RequestError)),
        wait=wait_random_exponential(multiplier=1.0, max=10.0),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def post_web_resource(
        self, session_id: str, url: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatches external HTTP POST request via cr-mcp-web-gateway with tenacity backoff & local httpx fallback."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)

        res_dict: Optional[Dict[str, Any]] = None

        tool = self._get_tool(session_id, "post_web_resource")
        if tool:
            try:
                raw_result = await tool.ainvoke({"url": url, "payload": payload})
                res_dict = self._parse_dict_response(raw_result)
            except Exception as e:
                err_str = str(e)
                logger.warning(f"MCP post_web_resource error: {err_str}")
                if "429" in err_str or "rate" in err_str.lower():
                    raise CentralaRateLimitError(f"MCP tool rate limit: {err_str}")
                match = re.search(r"(\{.*\})", err_str, re.DOTALL)
                if match:
                    try:
                        res_dict = json.loads(match.group(1))
                    except Exception:
                        pass
                if not res_dict:
                    code_val = 404 if "404" in err_str else 500
                    res_dict = {"status": "error", "code": code_val, "message": err_str[:300]}
        else:
            logger.error(f"MCP tool 'post_web_resource' unavailable for session {session_id}")
            res_dict = {"status": "error", "code": 503, "message": "MCP Web Gateway unavailable"}

        # Inspect if response payload contains Centrala rate limit code
        if isinstance(res_dict, dict):
            code = res_dict.get("code")
            msg = str(res_dict.get("message", "")).lower()
            if code == -9999 or "zwolnij" in msg or "za często" in msg or "too many requests" in msg:
                logger.warning(
                    f"Centrala rate limit detected (code={code}, msg='{res_dict.get('message')}'). Retrying via tenacity backoff..."
                )
                raise CentralaRateLimitError(f"Rate limited by Centrala: {res_dict.get('message')}")

        return res_dict

    async def write_file(
        self, session_id: str, file_path: str, content: str, reasoning: str
    ) -> Dict[str, Any]:
        """Writes text content to workspace file via cr-mcp-workspace with local fallback."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)

        tool = self._get_tool(session_id, "write_file")
        if tool:
            try:
                raw_result = await tool.ainvoke(
                    {"file_path": file_path, "content": content, "reasoning": reasoning}
                )
                return self._parse_dict_response(raw_result)
            except Exception as e:
                logger.warning(f"MCP write_file failed: {e}")

        # Local disk fallback
        local_target = self._local_workspace_base / session_id / file_path
        local_target.parent.mkdir(parents=True, exist_ok=True)
        local_target.write_text(content, encoding="utf-8")
        return {"status": "success", "file_path": str(local_target)}

    async def read_file(
        self, session_id: str, file_path: str, reasoning: str
    ) -> Dict[str, Any]:
        """Reads a text file from workspace via cr-mcp-workspace with local fallback."""
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
                logger.warning(f"MCP read_file failed: {e}")

        # Local disk fallback
        local_target = self._local_workspace_base / session_id / file_path
        if local_target.exists():
            return {"status": "success", "content": local_target.read_text(encoding="utf-8")}
        return {"status": "error", "error": f"File {file_path} not found"}
