import asyncio
import logging
import time
from typing import Any, Literal

import httpx

from config import settings
from schemas import (
    ActivateJumpResponse,
    CockpitControlsResponse,
    CockpitTelemetryResponse,
)

logger = logging.getLogger("cockpit_actuator")
logging.basicConfig(level=logging.INFO)


class CockpitActuator:
    """Manages physical time machine controls and cockpit execution."""

    def __init__(self) -> None:
        self.api_key = settings.AIDEVS_API_KEY
        self.backend_url = settings.AIDEVS_TIMETRAVEL_BACKEND_URL
        self.verify_url = settings.AIDEVS_API_VERIFY

    async def apply_controls(
        self,
        pta: bool,
        ptb: bool,
        pwr: int,
        mode: Literal["standby", "active"],
        session_id: str | None = None,
    ) -> CockpitControlsResponse:
        """Sets directional ports, shield PWR, and operating mode via cockpit protocol."""
        logger.info(
            "Applying cockpit controls: PTA=%s, PTB=%s, PWR=%d, mode=%s (session=%s)",
            pta,
            ptb,
            pwr,
            mode,
            session_id,
        )

        payload: dict[str, Any] = {
            "apikey": self.api_key,
            "PTA": pta,
            "PTB": ptb,
            "PWR": pwr,
            "mode": mode,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    self.backend_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                config = data.get("config", {})

                reported_flux = int(
                    config.get("fluxDensity") or config.get("flux") or 0
                )
                reported_pta = bool(config.get("PTA", pta))
                reported_ptb = bool(config.get("PTB", ptb))
                reported_pwr = int(config.get("PWR", pwr))
                reported_mode = config.get("mode", mode)

                logger.info(
                    "Cockpit controls applied successfully: flux=%d%%, mode=%s",
                    reported_flux,
                    reported_mode,
                )

                return CockpitControlsResponse(
                    success=True,
                    current_pta=reported_pta,
                    current_ptb=reported_ptb,
                    current_pwr=reported_pwr,
                    current_mode=reported_mode,
                    flux_density=reported_flux,
                    message="Controls successfully configured.",
                )
            except Exception as e:
                logger.error("Failed to apply cockpit controls: %s", e)
                return CockpitControlsResponse(
                    success=False,
                    current_pta=pta,
                    current_ptb=ptb,
                    current_pwr=pwr,
                    current_mode=mode,
                    flux_density=0,
                    message=f"Error applying controls: {e}",
                )

    async def get_telemetry(
        self, session_id: str | None = None
    ) -> CockpitTelemetryResponse:
        """Polls current cockpit hardware telemetry and gauge indicators."""
        logger.debug("Polling cockpit telemetry for session: %s", session_id)

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    self.backend_url,
                    params={"apikey": self.api_key},
                )
                resp.raise_for_status()
                data = resp.json()
                config = data.get("config", {})

                flux = int(config.get("fluxDensity") or config.get("flux") or 0)
                sync_display = int(config.get("syncRatio", 0))
                imode = int(config.get("internalMode", 1))
                battery = str(config.get("batteryStatus", "1/3"))
                condition = str(
                    config.get("condition", "STAN: NIESTABILNY // TRYB CZUWANIA")
                )
                mode = config.get("mode", "standby")
                pta = bool(config.get("PTA", False))
                ptb = bool(config.get("PTB", False))
                pwr = int(config.get("PWR", 0))

                orb_state = "ready" if flux == 100 else "danger"

                return CockpitTelemetryResponse(
                    flux_density=flux,
                    sync_ratio_display=sync_display,
                    current_imode=imode,
                    battery_status=battery,
                    orb_state=orb_state,
                    condition_text=condition,
                    mode=mode,
                    pta=pta,
                    ptb=ptb,
                    pwr=pwr,
                )
            except Exception as e:
                logger.error("Error retrieving telemetry: %s", e)
                return CockpitTelemetryResponse(
                    flux_density=0,
                    sync_ratio_display=0,
                    current_imode=1,
                    battery_status="unknown",
                    orb_state="danger",
                    condition_text=f"ERROR: {e}",
                    mode="standby",
                    pta=False,
                    ptb=False,
                    pwr=0,
                )

    async def activate_jump(
        self,
        target_imode: Literal[1, 2, 3, 4],
        timeout_seconds: float = 25.0,
        session_id: str | None = None,
    ) -> ActivateJumpResponse:
        """Waits for internalMode oscillation alignment and fires temporal displacement."""
        logger.info(
            "Awaiting internalMode=%d to trigger jump (timeout=%.1fs, session=%s)",
            target_imode,
            timeout_seconds,
            session_id,
        )

        start_time = time.monotonic()
        poll_interval = 0.5

        async with httpx.AsyncClient(timeout=15.0) as client:
            while (time.monotonic() - start_time) < timeout_seconds:
                # 1. Check current telemetry
                try:
                    t_resp = await client.get(
                        self.backend_url,
                        params={"apikey": self.api_key},
                    )
                    t_resp.raise_for_status()
                    cfg = t_resp.json().get("config", {})
                    current_imode = int(cfg.get("internalMode", 0))
                    flux = int(cfg.get("fluxDensity") or cfg.get("flux") or 0)

                    logger.debug(
                        "Polling phase: current_imode=%d (target=%d), flux=%d%%",
                        current_imode,
                        target_imode,
                        flux,
                    )

                    # 2. Phase and flux alignment check
                    if current_imode == target_imode:
                        if flux < 100:
                            logger.info(
                                "Target phase reached (imode=%d), but flux is %d%% (waiting for 100%%)...",
                                current_imode,
                                flux,
                            )
                            await asyncio.sleep(poll_interval)
                            continue

                        logger.info(
                            "Core alignment achieved! imode=%d, flux=%d%%. Actuating ignition orb.",
                            current_imode,
                            flux,
                        )

                        # Trigger time displacement via Central verification gateway
                        verify_payload = {
                            "apikey": self.api_key,
                            "task": "timetravel",
                            "answer": {"action": "timeTravel"},
                        }

                        jump_resp = await client.post(
                            self.verify_url,
                            json=verify_payload,
                            headers={"Content-Type": "application/json"},
                        )
                        jump_data = jump_resp.json()

                        logger.info(
                            "Ignition response received from Central: status=%d, payload=%s",
                            jump_resp.status_code,
                            jump_data,
                        )

                        code = jump_data.get("code")
                        flag = jump_data.get("flag")
                        message = jump_data.get("message", "Jump executed.")
                        battery = jump_data.get("config", {}).get("batteryStatus")

                        if jump_resp.is_success and (code == 13 or flag is not None):
                            return ActivateJumpResponse(
                                success=True,
                                jump_code=code,
                                battery_status=battery,
                                flag=flag,
                                message=message,
                            )
                        else:
                            return ActivateJumpResponse(
                                success=False,
                                jump_code=code,
                                battery_status=battery,
                                flag=flag,
                                message=f"Jump rejected: {message}",
                            )

                except Exception as e:
                    logger.warning("Transient error during phase polling: %s", e)

                await asyncio.sleep(poll_interval)

        return ActivateJumpResponse(
            success=False,
            jump_code=None,
            battery_status=None,
            flag=None,
            message=f"Timeout waiting for internalMode={target_imode} after {timeout_seconds}s.",
        )


actuator = CockpitActuator()
