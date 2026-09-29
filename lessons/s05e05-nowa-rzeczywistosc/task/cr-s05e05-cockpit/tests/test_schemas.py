import pytest
from pydantic import ValidationError

from schemas import (
    ActivateJumpRequest,
    ActivateJumpResponse,
    CockpitControlsRequest,
    CockpitTelemetryResponse,
)


def test_cockpit_controls_request_valid() -> None:
    req = CockpitControlsRequest(
        pta=False,
        ptb=True,
        pwr=91,
        mode="active",
        session_id="test-session",
    )
    assert req.pta is False
    assert req.ptb is True
    assert req.pwr == 91
    assert req.mode == "active"


def test_cockpit_controls_request_pwr_bounds() -> None:
    with pytest.raises(ValidationError):
        CockpitControlsRequest(pta=True, ptb=False, pwr=101, mode="standby")

    with pytest.raises(ValidationError):
        CockpitControlsRequest(pta=True, ptb=False, pwr=-1, mode="standby")


def test_activate_jump_request_valid() -> None:
    req = ActivateJumpRequest(
        target_imode=3,
        timeout_seconds=20.0,
        session_id="test-jump",
    )
    assert req.target_imode == 3
    assert req.timeout_seconds == 20.0


def test_activate_jump_response() -> None:
    resp = ActivateJumpResponse(
        success=True,
        jump_code=13,
        battery_status="3/3",
        flag="{FLG:TEST}",
        message="Jump success",
    )
    assert resp.success is True
    assert resp.jump_code == 13
    assert resp.battery_status == "3/3"


def test_cockpit_telemetry_response() -> None:
    telemetry = CockpitTelemetryResponse(
        flux_density=100,
        sync_ratio_display=82,
        current_imode=3,
        battery_status="1/3",
        orb_state="ready",
        condition_text="STAN: DOSKONAŁY",
        mode="active",
        pta=False,
        ptb=True,
        pwr=91,
    )
    assert telemetry.flux_density == 100
    assert telemetry.current_imode == 3
