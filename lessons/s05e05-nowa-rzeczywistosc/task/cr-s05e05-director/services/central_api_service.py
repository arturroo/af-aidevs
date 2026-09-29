import asyncio
import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger("central_api")


class CentralApiService:
    """Interfaces with Central verify gateway ($AIDEVS_API_VERIFY) for CHRONOS-P1 registers."""

    def __init__(self) -> None:
        self.api_key = settings.AIDEVS_API_KEY
        self.verify_url = settings.AIDEVS_API_VERIFY

    async def _post(
        self, answer_payload: dict[str, Any], max_retries: int = 3
    ) -> dict[str, Any]:
        """Dispatches an envelope payload to Central /verify with retry backoff."""
        envelope = {
            "apikey": self.api_key,
            "task": "timetravel",
            "answer": answer_payload,
        }

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        self.verify_url,
                        json=envelope,
                        headers={"Content-Type": "application/json"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    logger.info(
                        "Central API response (action=%s): %s",
                        answer_payload.get("action"),
                        data,
                    )
                    return data
            except httpx.HTTPStatusError as e:
                err_body = e.response.text[:300] if e.response is not None else ""
                logger.warning(
                    "Central API error on attempt %d/%d (action=%s): HTTP %s - %s | Body: %s",
                    attempt,
                    max_retries,
                    answer_payload.get("action"),
                    e.response.status_code if e.response is not None else 0,
                    e,
                    err_body,
                )
                if attempt == max_retries:
                    raise
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
            except httpx.RequestError as e:
                logger.warning(
                    "Central API network error on attempt %d/%d (action=%s): %s",
                    attempt,
                    max_retries,
                    answer_payload.get("action"),
                    e,
                )
                if attempt == max_retries:
                    raise
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
        return {}

    async def get_help(self) -> dict[str, Any]:
        """Queries API documentation help from Central."""
        logger.info("Querying Central help action...")
        return await self._post({"action": "help"})

    async def get_config(self) -> dict[str, Any]:
        """Queries current hardware register configuration and stabilization hints."""
        logger.info("Querying Central getConfig action...")
        return await self._post({"action": "getConfig"})

    async def configure(self, param: str, value: Any) -> dict[str, Any]:
        """Sets a discrete temporal register (day, month, year, syncRatio, stabilization)."""
        logger.info("Configuring Central register: %s = %s", param, value)
        return await self._post({"action": "configure", "param": param, "value": value})

    async def reset(self) -> dict[str, Any]:
        """Triggers emergency hardware reset on Central device."""
        logger.info("Triggering Central emergency reset action...")
        return await self._post({"action": "reset"})


central_api = CentralApiService()
