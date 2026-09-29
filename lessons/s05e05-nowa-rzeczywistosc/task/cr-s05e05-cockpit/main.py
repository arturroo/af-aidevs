import logging

from fastapi import FastAPI

from schemas import (
    ActivateJumpRequest,
    ActivateJumpResponse,
    CockpitControlsRequest,
    CockpitControlsResponse,
    CockpitTelemetryResponse,
)
from services.browser_actuator import actuator

logger = logging.getLogger("cockpit_service")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="cr-s05e05-cockpit",
    version="0.1.0",
    description="Physical Cockpit Actuator Microservice for CHRONOS-P1",
)


@app.get("/health")
@app.get("/")
async def health_check() -> dict[str, str]:
    """Canonical health check and service readiness status endpoint."""
    return {
        "status": "healthy",
        "service": "cr-s05e05-cockpit",
        "version": "0.1.0",
    }


@app.post("/controls", response_model=CockpitControlsResponse)
async def apply_controls(
    request: CockpitControlsRequest,
) -> CockpitControlsResponse:
    """Configures physical switches (PTA, PTB, PWR potentiometer, operating mode)."""
    return await actuator.apply_controls(
        pta=request.pta,
        ptb=request.ptb,
        pwr=request.pwr,
        mode=request.mode,
        session_id=request.session_id,
    )


@app.get("/telemetry", response_model=CockpitTelemetryResponse)
async def get_telemetry(
    session_id: str | None = None,
) -> CockpitTelemetryResponse:
    """Reads real-time cockpit instrument readings (flux density, sync ratio, imode, battery)."""
    return await actuator.get_telemetry(session_id=session_id)


@app.post("/activate-jump", response_model=ActivateJumpResponse)
async def activate_jump(
    request: ActivateJumpRequest,
) -> ActivateJumpResponse:
    """Awaits internalMode phase alignment and actuates the temporal ignition orb."""
    return await actuator.activate_jump(
        target_imode=request.target_imode,
        timeout_seconds=request.timeout_seconds,
        session_id=request.session_id,
    )
