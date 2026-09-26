import logging
from typing import Any

import httpx

import config

logger = logging.getLogger("services.model_armor")


class ModelArmorService:
    """Guardrail service validating untrusted texts and database schemas against indirect prompt injection."""

    def __init__(self, armor_url: str | None = None):
        self.armor_url = armor_url or config.MODEL_ARMOR_URL

    async def scan_text(self, text: str, context: str = "transcript") -> dict[str, Any]:
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
                    f"Model Armor returned status {resp.status_code}: {resp.text}"
                )
        except Exception as e:
            logger.debug(f"Model Armor check bypassed due to network error ({e})")

        return {"is_safe": True, "bypassed": True, "threats": []}
