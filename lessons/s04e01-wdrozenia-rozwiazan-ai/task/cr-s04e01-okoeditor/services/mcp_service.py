import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
from af_aidevs.clients.mcp import get_all_mcp_tools
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

import config

logger = logging.getLogger("services.mcp")


class CentralaRateLimitError(Exception):
    """Raised when Centrala returns rate limit code -9999 or 429 throttle signal."""


class MCPService:
    """Unified client connecting to cr-mcp-web-gateway and cr-mcp-workspace via af_aidevs."""

    def __init__(
        self,
        workspace_url: str | None = None,
        web_url: str | None = None,
    ):
        self.workspace_url = workspace_url or config.MCP_WORKSPACE_URL
        self.web_url = web_url or config.MCP_WEB_GATEWAY_URL
        self._tools_cache: dict[str, dict[str, Any]] = {}
        self._local_workspace_base = Path("/tmp/af_aidevs_workspace")

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
                f"Failed to connect to remote MCP servers ({e}). Using local fallback."
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
        """Extracts underlying content or dict from LangChain/MCP tool output."""
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

    @retry(
        retry=retry_if_exception_type(
            (CentralaRateLimitError, httpx.HTTPStatusError, httpx.RequestError)
        ),
        wait=wait_random_exponential(multiplier=1.0, max=10.0),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def post_web_resource(
        self, session_id: str, url: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatches external HTTP POST request via cr-mcp-web-gateway with tenacity backoff & direct httpx fallback."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)

        res_dict: dict[str, Any] | None = None

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
                    # Fallback to direct httpx request if MCP call fails locally
                    logger.info(f"Attempting direct httpx fallback for {url}")
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.post(url, json=payload)
                        res_dict = resp.json()
        else:
            # Fallback to direct httpx if MCP gateway is not available locally
            logger.info(f"MCP gateway not available, attempting direct httpx for {url}")
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, json=payload)
                    res_dict = resp.json()
            except Exception as ex:
                res_dict = {"status": "error", "code": 503, "message": str(ex)}

        # Inspect if response payload contains Centrala rate limit code
        if isinstance(res_dict, dict):
            code = res_dict.get("code")
            msg = str(res_dict.get("message", "")).lower()
            if (
                code == -9999
                or "zwolnij" in msg
                or "za często" in msg
                or "too many requests" in msg
            ):
                logger.warning(
                    f"Centrala rate limit detected (code={code}, msg='{res_dict.get('message')}'). Retrying via tenacity backoff..."
                )
                raise CentralaRateLimitError(
                    f"Rate limited by Centrala: {res_dict.get('message')}"
                )

        return res_dict or {}

    async def write_file(
        self, session_id: str, file_path: str, content: str, reasoning: str
    ) -> dict[str, Any]:
        """Writes text content to workspace file via cr-mcp-workspace with local disk fallback."""
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
    ) -> dict[str, Any]:
        """Reads a text file from workspace via cr-mcp-workspace with local disk fallback."""
        try:
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
                if local_target.is_dir():
                    return {
                        "status": "error",
                        "error": f"Path '{file_path}' is a directory. Use list_workspace_files to view directory contents.",
                        "hint": "Use list_workspace_files to view files in a directory.",
                    }
                return {
                    "status": "success",
                    "content": local_target.read_text(encoding="utf-8"),
                }
            return {"status": "error", "error": f"File {file_path} not found"}
        except Exception as e:
            logger.error(f"Error in read_file for '{file_path}': {e}")
            return {"status": "error", "error": str(e)}

    async def list_files(
        self, session_id: str, path: str = ".", reasoning: str = ""
    ) -> dict[str, Any]:
        """Lists files and directories in workspace via cr-mcp-workspace with local disk fallback."""
        try:
            if session_id not in self._tools_cache:
                await self.get_tools_for_session(session_id)

            tool = self._get_tool(session_id, "list_files")
            if tool:
                try:
                    raw_result = await tool.ainvoke(
                        {"path": path, "reasoning": reasoning}
                    )
                    return self._parse_dict_response(raw_result)
                except Exception as e:
                    logger.warning(f"MCP list_files failed: {e}")

            # Local disk fallback
            target_dir = (self._local_workspace_base / session_id / path).resolve()
            if not target_dir.exists():
                return {
                    "status": "error",
                    "error": f"Directory '{path}' not found.",
                    "files": [],
                    "hint": "Check if directory exists. Use '.' to list workspace root.",
                }

            files = []
            for item in target_dir.iterdir():
                try:
                    is_dir = item.is_dir()
                    files.append(
                        {
                            "name": item.name,
                            "type": "directory" if is_dir else "file",
                            "size_bytes": item.stat().st_size if not is_dir else 0,
                        }
                    )
                except Exception:
                    continue

            return {"status": "success", "files": files}
        except Exception as e:
            logger.error(f"Error in list_files for '{path}': {e}")
            return {"status": "error", "error": str(e), "files": []}
