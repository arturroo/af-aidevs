import json
import logging
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
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
from tenacity.wait import wait_base

import config

logger = logging.getLogger("services.mcp")


def parse_retry_after(header_val: str | None) -> float | None:
    """Parses Retry-After value as either seconds (float) or an RFC 7231 HTTP-date."""
    if not header_val:
        return None
    cleaned = str(header_val).strip()
    try:
        val = float(cleaned)
        return max(0.0, val)
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(cleaned)
        delta = (dt - datetime.now(UTC)).total_seconds()
        return max(0.0, delta)
    except Exception:
        return None


class CentralaRateLimitError(Exception):
    """Raised when Centrala returns HTTP 429, application code -9999, or throttle message."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class CentralaServerError(Exception):
    """Raised when Centrala or upstream service returns HTTP >= 500 or payload error code >= 500."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


class wait_retry_after_or_exponential(wait_base):
    """Tenacity wait strategy: honors explicit Retry-After delay if present, otherwise uses exponential jitter."""

    def __init__(
        self,
        multiplier: float = 1.0,
        min_wait: float = 1.0,
        max_wait: float = 15.0,
    ):
        self.fallback = wait_random_exponential(
            multiplier=multiplier, min=min_wait, max=max_wait
        )

    def __call__(self, retry_state: Any) -> float:
        if retry_state.outcome and retry_state.outcome.failed:
            exc = retry_state.outcome.exception()
            if (
                isinstance(exc, CentralaRateLimitError)
                and exc.retry_after is not None
                and exc.retry_after > 0
            ):
                logger.info(
                    f"Honoring explicit Retry-After from server: {exc.retry_after:.2f}s"
                )
                return float(exc.retry_after)
        return float(self.fallback(retry_state))


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
        if isinstance(result, list) and len(result) > 0:
            return MCPService._extract_raw(result[0])
        return result

    @staticmethod
    def _parse_dict_response(raw: Any) -> dict[str, Any]:
        """Safely parses tool output into a dictionary."""
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

    @retry(
        retry=retry_if_exception_type(
            (
                CentralaRateLimitError,
                CentralaServerError,
                httpx.HTTPStatusError,
                httpx.RequestError,
            )
        ),
        wait=wait_retry_after_or_exponential(
            multiplier=1.0, min_wait=1.0, max_wait=15.0
        ),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def post_web_resource(
        self, session_id: str, url: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatches external HTTP POST request via cr-mcp-web-gateway with resilience & tenacity backoff."""
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
                if (
                    "429" in err_str
                    or "rate" in err_str.lower()
                    or "zwolnij" in err_str.lower()
                ):
                    retry_match = re.search(
                        r"retry[-_]after[:\s=]+(\d+(?:\.\d+)?)", err_str, re.IGNORECASE
                    )
                    retry_val = float(retry_match.group(1)) if retry_match else None
                    raise CentralaRateLimitError(
                        f"MCP tool rate limit: {err_str}", retry_after=retry_val
                    ) from e
                code_match = re.search(r"\b(50[0-9]|5[1-9][0-9])\b", err_str)
                if code_match:
                    raise CentralaServerError(
                        f"MCP tool server error: {err_str}",
                        status_code=int(code_match.group(1)),
                    ) from e
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
                        retry_after = parse_retry_after(resp.headers.get("retry-after"))
                        if resp.status_code == 429:
                            raise CentralaRateLimitError(
                                f"HTTP 429 Too Many Requests from {url}",
                                retry_after=retry_after,
                            )
                        if resp.status_code >= 500:
                            raise CentralaServerError(
                                f"HTTP {resp.status_code} Server Error from {url}: {resp.text[:300]}",
                                status_code=resp.status_code,
                            )
                        res_dict = resp.json()
        else:
            # Fallback to direct httpx if MCP gateway is not available locally
            logger.info(f"MCP gateway not available, attempting direct httpx for {url}")
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload)
                retry_after = parse_retry_after(resp.headers.get("retry-after"))
                if resp.status_code == 429:
                    raise CentralaRateLimitError(
                        f"HTTP 429 Too Many Requests from {url}",
                        retry_after=retry_after,
                    )
                if resp.status_code >= 500:
                    raise CentralaServerError(
                        f"HTTP {resp.status_code} Server Error from {url}: {resp.text[:300]}",
                        status_code=resp.status_code,
                    )
                res_dict = resp.json()

        # Inspect if response payload contains rate limit or server error codes
        if isinstance(res_dict, dict):
            code = res_dict.get("code")
            status = res_dict.get("status")
            msg = str(res_dict.get("message", "")).lower()

            # 1. Rate limits: code -9999, 429, or throttling phrases
            if (
                code == -9999
                or code == 429
                or status == 429
                or "zwolnij" in msg
                or "za często" in msg
                or "too many requests" in msg
                or "rate limit" in msg
            ):
                retry_after = parse_retry_after(
                    str(res_dict.get("retry_after") or res_dict.get("retryAfter") or "")
                )
                if retry_after is None:
                    delay_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:s|sek|sec)", msg)
                    if delay_match:
                        retry_after = float(delay_match.group(1))

                logger.warning(
                    f"Centrala rate limit detected (code={code}, retry_after={retry_after}, msg='{res_dict.get('message')}'). Retrying..."
                )
                raise CentralaRateLimitError(
                    f"Rate limited by Centrala (code={code}): {res_dict.get('message')}",
                    retry_after=retry_after,
                )

            # 2. Server errors: code >= 500 or status >= 500
            if (isinstance(code, int) and code >= 500) or (
                isinstance(status, int) and status >= 500
            ):
                err_code = (
                    code if isinstance(code, int) and code >= 500 else int(status)  # type: ignore
                )
                logger.warning(
                    f"Centrala server error detected (code={err_code}, msg='{res_dict.get('message')}'). Retrying..."
                )
                raise CentralaServerError(
                    f"Server error from Centrala (code={err_code}): {res_dict.get('message')}",
                    status_code=err_code,
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
        return {
            "status": "success",
            "file_path": str(local_target),
            "bytes_written": len(content),
        }

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
                    parsed = self._parse_dict_response(raw_result)
                    if "content" in parsed:
                        return parsed
                except Exception as e:
                    logger.warning(f"MCP read_file failed: {e}")

            # Local disk fallback
            local_target = self._local_workspace_base / session_id / file_path
            if local_target.exists():
                return {
                    "status": "success",
                    "file_path": file_path,
                    "content": local_target.read_text(encoding="utf-8"),
                }
            return {
                "status": "not_found",
                "file_path": file_path,
                "content": "",
            }
        except Exception as e:
            return {"status": "error", "file_path": file_path, "message": str(e)}
