import logging
from typing import Any

import httpx

import config

logger = logging.getLogger("services.centrala")


class CentralaService:
    """Client for Centrala verification API ($AIDEVS_API_VERIFY)."""

    def __init__(
        self,
        api_url: str = config.AIDEVS_API_VERIFY,
        api_key: str = config.AIDEVS_API_KEY,
    ) -> None:
        self.api_url = api_url
        self.api_key = api_key
        if not self.api_url:
            logger.warning("AIDEVS_API_VERIFY is not set in environment!")
        if not self.api_key:
            logger.warning("AIDEVS_API_KEY is not set in environment!")

    async def start_call(self) -> dict[str, Any]:
        """Initiate the phonecall conversation session with Centrala."""
        payload = {
            "apikey": self.api_key,
            "task": "phonecall",
            "answer": {"action": "start"},
        }

        logger.info(
            f"Starting phonecall session via POST {self.api_url} (task=phonecall, action=start)"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.api_url, json=payload)

        status_code = resp.status_code
        logger.info(f"Centrala start response status: {status_code}")

        try:
            data = resp.json()
            logger.info(f"Centrala start response body: {data}")
        except Exception as e:
            logger.error(
                f"Failed to parse Centrala start response JSON: {e}, text: {resp.text[:300]}"
            )
            return {
                "code": -1,
                "message": f"HTTP {status_code} parse error: {resp.text[:200]}",
            }

        return data

    async def send_audio_turn(self, audio_base64: str) -> dict[str, Any]:
        """Send an audio turn to Centrala with Base64 payload masking in logs."""
        masked_preview = f"<REDACTED_BASE64: length={len(audio_base64)} chars, ~{len(audio_base64) * 3 // 4 // 1024} KB>"
        logger.info(f"Sending audio turn to Centrala: audio={masked_preview}")

        payload = {
            "apikey": self.api_key,
            "task": "phonecall",
            "answer": {"audio": audio_base64},
        }

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(self.api_url, json=payload)

        status_code = resp.status_code
        logger.info(f"Centrala turn response status: {status_code}")

        try:
            data = resp.json()
        except Exception as e:
            logger.error(
                f"Failed to parse Centrala turn response JSON: {e}, text: {resp.text[:300]}"
            )
            return {
                "code": -1,
                "message": f"HTTP {status_code} parse error: {resp.text[:200]}",
            }

        # Mask audio in response logs if returned
        resp_audio = data.get("audio")
        if resp_audio and isinstance(resp_audio, str):
            resp_audio_masked = f"<REDACTED_BASE64: length={len(resp_audio)} chars, ~{len(resp_audio) * 3 // 4 // 1024} KB>"
            logger.info(
                f"Centrala returned audio response: code={data.get('code')}, audio={resp_audio_masked}, message={data.get('message', '')[:100]}"
            )
        else:
            logger.info(
                f"Centrala returned response: code={data.get('code')}, message={data.get('message', '')[:100]}"
            )

        return data
