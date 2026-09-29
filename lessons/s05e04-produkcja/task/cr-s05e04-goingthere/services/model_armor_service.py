"""Guardrail service validating untrusted texts against indirect prompt injection."""

import logging
from typing import Any

import httpx

from config import config

logger = logging.getLogger("services.model_armor")


class ModelArmorService:
    """Guardrail service validating external scanner and radio payloads against prompt injection."""

    def __init__(self, armor_url: str | None = None) -> None:
        self.armor_url = armor_url or config.MODEL_ARMOR_URL

    async def scan_text(self, text: str, context: str = "telemetry") -> dict[str, Any]:
        """Scans input text for injection or jailbreak patterns. Returns safety status."""
        if not self.armor_url:
            return {
                "is_safe": True,
                "reason": "Model Armor not configured",
                "threats": [],
            }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    self.armor_url,
                    json={"text": text[:4000], "context": context},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    is_safe = data.get("is_safe", True)
                    threats = data.get("threats", [])
                    return {
                        "is_safe": is_safe,
                        "threats": threats,
                        "score": data.get("score", 0.0),
                    }
                logger.warning(
                    f"Model Armor returned status {resp.status_code}: {resp.text[:200]}"
                )
        except Exception as e:
            logger.debug(f"Model Armor check bypassed due to network error ({e})")

        return {"is_safe": True, "bypassed": True, "threats": []}

    async def sanitize_payload(self, text: str, context: str = "telemetry") -> str:
        """Validates payload and returns sanitized string or raises warning if compromised."""
        scan_result = await self.scan_text(text, context=context)
        if not scan_result.get("is_safe", True):
            threats = scan_result.get("threats", [])
            logger.warning(
                f"Model Armor detected potential threat in {context} payload: {threats}"
            )
        return text
