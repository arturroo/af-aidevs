"""Gateway and egress service mediating outbound requests to course endpoints."""

import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from config import config

logger = logging.getLogger("services.gateway")


class GatewayTransientError(Exception):
    """Raised on transient HTTP errors (429, 5xx) to trigger tenacity retry."""


class GatewayService:
    """Outbound communication service routing requests via cr-mcp-web-gateway or direct httpx."""

    def __init__(
        self,
        direct_egress: bool = False,
        timeout: float = 30.0,
    ) -> None:
        self.direct_egress = direct_egress or not bool(config.MCP_WEB_GATEWAY_URL)
        self.timeout = timeout
        self.web_gateway_url = config.MCP_WEB_GATEWAY_URL

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, GatewayTransientError)),
        wait=wait_random_exponential(multiplier=1.0, max=10.0),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def get(self, url: str, params: dict[str, Any] | None = None) -> str:
        """Executes HTTP GET with retries, returning response text."""
        headers = {"User-Agent": "cr-s05e04-goingthere"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise GatewayTransientError(
                    f"Transient HTTP {resp.status_code} from {url}: {resp.text[:200]}"
                )
            resp.raise_for_status()
            return resp.text

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, GatewayTransientError)),
        wait=wait_random_exponential(multiplier=1.0, max=10.0),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def post_json(self, url: str, json_data: dict[str, Any]) -> dict[str, Any]:
        """Executes HTTP POST with JSON payload and retries, returning parsed JSON dict."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "cr-s05e04-goingthere",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=json_data, headers=headers)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise GatewayTransientError(
                    f"Transient HTTP {resp.status_code} from {url}: {resp.text[:200]}"
                )
            if resp.status_code >= 400:
                logger.error(
                    f"Centrala gateway returned HTTP {resp.status_code} from {url}: {resp.text}"
                )
                try:
                    return resp.json()
                except Exception:
                    pass
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception:
                return {"raw_text": resp.text}

    async def get_scanner_status(self, api_key: str) -> str:
        """Polls frequency scanner GET endpoint."""
        url = config.frequency_scanner_url
        if not url:
            raise ValueError("Frequency scanner URL is not configured or derivable!")
        return await self.get(url, params={"key": api_key})

    async def post_disarm(
        self, api_key: str, frequency: float, disarm_hash: str
    ) -> dict[str, Any]:
        """Submits disarm payload to frequency scanner POST endpoint."""
        url = config.frequency_scanner_url
        if not url:
            raise ValueError("Frequency scanner URL is not configured or derivable!")
        payload = {
            "apikey": api_key,
            "frequency": frequency,
            "disarmHash": disarm_hash,
        }
        return await self.post_json(url, payload)

    async def post_getmessage(self, api_key: str) -> dict[str, Any]:
        """Requests tactical radio broadcast hint."""
        url = config.getmessage_url
        if not url:
            raise ValueError(
                "GetMessage radio hint URL is not configured or derivable!"
            )
        return await self.post_json(url, {"apikey": api_key})

    async def post_verify(self, command: str, api_key: str) -> dict[str, Any]:
        """Dispatches movement or start command to Centrala verify gateway."""
        url = config.AIDEVS_API_VERIFY
        if not url:
            raise ValueError("AIDEVS_API_VERIFY is not configured!")
        payload = {
            "apikey": api_key,
            "task": config.TASK_NAME,
            "answer": {"command": command},
        }
        return await self.post_json(url, payload)
