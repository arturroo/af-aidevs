import logging
from typing import Any

import google.auth.transport.requests
import google.oauth2.id_token
import httpx

from config import settings

logger = logging.getLogger("cockpit_client")


class CockpitClient:
    """Agent-to-Agent (A2A) private HTTP client communicating with cr-s05e05-cockpit."""

    def __init__(self) -> None:
        self.base_url = settings.COCKPIT_SERVICE_URL.strip().rstrip("/")

    def _get_auth_headers(self) -> dict[str, str]:
        """Generates Google Cloud IAM OIDC bearer token for private Cloud Run service invocation."""
        headers = {"Content-Type": "application/json"}
        # If invoking a remote Cloud Run endpoint (.run.app), generate an OIDC token
        if "run.app" in self.base_url:
            try:
                auth_req = google.auth.transport.requests.Request()
                token = google.oauth2.id_token.fetch_id_token(auth_req, self.base_url)
                headers["Authorization"] = f"Bearer {token}"
                logger.debug("Generated IAM OIDC token for %s", self.base_url)
            except Exception as e:
                logger.warning(
                    "Unable to acquire Google Cloud OIDC token for %s: %s",
                    self.base_url,
                    e,
                )
        return headers

    async def set_controls(
        self,
        pta: bool,
        ptb: bool,
        pwr: int,
        mode: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Invokes POST /controls on the Cockpit service."""
        url = f"{self.base_url}/controls"
        headers = self._get_auth_headers()
        payload = {
            "session_id": session_id,
            "pta": pta,
            "ptb": ptb,
            "pwr": pwr,
            "mode": mode,
        }

        logger.info(
            "A2A dispatch: POST /controls -> PTA=%s, PTB=%s, PWR=%d, mode=%s",
            pta,
            ptb,
            pwr,
            mode,
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            logger.info("A2A response /controls: %s", data)
            return data

    async def get_telemetry(self, session_id: str | None = None) -> dict[str, Any]:
        """Invokes GET /telemetry on the Cockpit service."""
        url = f"{self.base_url}/telemetry"
        headers = self._get_auth_headers()
        params = {"session_id": session_id} if session_id else {}

        logger.debug("A2A dispatch: GET /telemetry")

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def activate_jump(
        self,
        target_imode: int,
        timeout_seconds: float = 25.0,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Invokes POST /activate-jump on the Cockpit service."""
        url = f"{self.base_url}/activate-jump"
        headers = self._get_auth_headers()
        payload = {
            "session_id": session_id,
            "target_imode": target_imode,
            "timeout_seconds": timeout_seconds,
        }

        logger.info(
            "A2A dispatch: POST /activate-jump -> target_imode=%d, timeout=%.1fs",
            target_imode,
            timeout_seconds,
        )

        # Longer timeout on client since Cockpit polls phase cycle
        async with httpx.AsyncClient(timeout=timeout_seconds + 10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            logger.info("A2A response /activate-jump: %s", data)
            return data


cockpit_client = CockpitClient()
