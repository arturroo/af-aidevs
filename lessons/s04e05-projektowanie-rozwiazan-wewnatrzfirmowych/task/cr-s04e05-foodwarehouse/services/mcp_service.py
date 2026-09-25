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
from services.centrala_service import CentralaRateLimitError

logger = logging.getLogger("services.mcp")


class MCPService:
    """Unified client connecting to cr-mcp-workspace and cr-mcp-web-gateway via af_aidevs with local fallback."""

    def __init__(
        self,
        workspace_url: str | None = None,
        web_url: str | None = None,
        local_base: Path | None = None,
    ):
        self.workspace_url = workspace_url or config.MCP_WORKSPACE_URL
        self.web_url = web_url or config.MCP_WEB_GATEWAY_URL
        self.local_base = local_base or config.LOCAL_WORKSPACE_DIR
        self._tools_cache: dict[str, dict[str, Any]] = {}
        self.local_base.mkdir(parents=True, exist_ok=True)

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
        """Extracts underlying content or dict from LangChain/MCP tool output."""
        if hasattr(result, "content"):
            return MCPService._extract_raw(result.content)
        if isinstance(result, list) and len(result) > 0:
            return MCPService._extract_raw(result[0])
        return result

    @staticmethod
    def _parse_dict_response(raw: Any) -> dict[str, Any]:
        """Safely parses tool output into a dictionary."""
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
            return {"raw_output": text}
        return {"raw_output": str(raw)}

    def _resolve_local_path(self, session_id: str, file_path: str) -> Path:
        """Resolves local fallback path guaranteeing isolation by session_id."""
        clean_sub = file_path.lstrip("/").replace("\\", "/")
        base = self.local_base / session_id
        resolved = (base / clean_sub).resolve()
        if not str(resolved).startswith(str(base.resolve())):
            raise ValueError(f"Path traversal detected: {file_path}")
        return resolved

    async def write_file(
        self,
        session_id: str,
        file_path: str,
        content: str,
        reasoning: str = "",
    ) -> dict[str, Any]:
        """Writes or updates a file in cr-mcp-workspace with local fallback."""
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
                    try:
                        inner = json.loads(parsed["text"])
                        if isinstance(inner, dict) and "content" in inner:
                            return str(inner["content"])
                    except Exception:
                        pass
                    return str(parsed["text"])
                raw_text = self._extract_raw(raw_result)
                if isinstance(raw_text, str):
                    try:
                        parsed_raw = json.loads(raw_text)
                        if isinstance(parsed_raw, dict) and "content" in parsed_raw:
                            return str(parsed_raw["content"])
                    except Exception:
                        pass
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
                if isinstance(parsed, dict) and "files" in parsed:
                    for item in parsed["files"]:
                        name = (
                            str(item.get("name", item))
                            if isinstance(item, dict)
                            else str(item)
                        )
                        if name:
                            file_list.append(name)
                elif isinstance(parsed, list):
                    file_list = [str(x) for x in parsed]
                return file_list
            except Exception as e:
                logger.warning(f"MCP list_files failed ({e}), using local fallback.")

        base = self._resolve_local_path(session_id, clean_path)
        if not base.exists():
            return []
        return [
            str(p.relative_to(base)).replace("\\", "/")
            for p in base.rglob("*")
            if p.is_file()
        ]

    @retry(
        retry=retry_if_exception_type(
            (CentralaRateLimitError, httpx.HTTPStatusError, httpx.RequestError)
        ),
        wait=wait_random_exponential(multiplier=1.0, min=1.0, max=10.0),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def post_web_resource(
        self,
        url: str,
        json_payload: dict[str, Any],
        session_id: str = "default",
    ) -> dict[str, Any]:
        """Dispatches external HTTP POST request via cr-mcp-web-gateway with tenacity backoff."""
        if session_id not in self._tools_cache:
            await self.get_tools_for_session(session_id)

        tool = self._get_tool(session_id, "post_web_resource")
        if tool:
            try:
                raw_result = await tool.ainvoke({"url": url, "payload": json_payload})
                res_dict = self._parse_dict_response(raw_result)
                code = res_dict.get("code", 0)
                msg = str(res_dict.get("message", ""))
                if (
                    code == -9999
                    or "rate limit" in msg.lower()
                    or "throttle" in msg.lower()
                ):
                    logger.warning(f"MCP gateway rate limit hit: {msg}")
                    raise CentralaRateLimitError(msg)
                return res_dict
            except CentralaRateLimitError:
                raise
            except Exception as e:
                logger.warning(
                    f"MCP post_web_resource failed ({e}), falling back to direct httpx."
                )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=json_payload)
            if resp.status_code == 429:
                raise CentralaRateLimitError("HTTP 429 Too Many Requests")
            try:
                return resp.json()
            except Exception:
                return {"code": resp.status_code, "message": resp.text}
