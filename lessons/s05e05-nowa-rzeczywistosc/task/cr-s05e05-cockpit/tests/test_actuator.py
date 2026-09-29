from unittest.mock import patch

import httpx
import pytest

from services.browser_actuator import CockpitActuator


@pytest.mark.asyncio
async def test_apply_controls_mocked() -> None:
    actuator = CockpitActuator()
    mock_response = {
        "config": {
            "PTA": False,
            "PTB": True,
            "PWR": 91,
            "mode": "active",
            "flux": 100,
        }
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = httpx.Response(
            200,
            json=mock_response,
            request=httpx.Request("POST", "https://hub.ag3nts.org/timetravel_backend"),
        )
        res = await actuator.apply_controls(pta=False, ptb=True, pwr=91, mode="active")
        assert res.success is True
        assert res.current_pta is False
        assert res.current_ptb is True
        assert res.current_pwr == 91
        assert res.flux_density == 100


@pytest.mark.asyncio
async def test_get_telemetry_mocked() -> None:
    actuator = CockpitActuator()
    mock_response = {
        "config": {
            "PTA": True,
            "PTB": True,
            "PWR": 19,
            "mode": "active",
            "flux": 100,
            "syncRatio": 54,
            "internalMode": 2,
            "batteryStatus": "2/3",
            "condition": "STAN: DOSKONAŁY // TRYB AKTYWNY",
        }
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = httpx.Response(
            200,
            json=mock_response,
            request=httpx.Request("GET", "https://hub.ag3nts.org/timetravel_backend"),
        )
        res = await actuator.get_telemetry()
        assert res.flux_density == 100
        assert res.current_imode == 2
        assert res.sync_ratio_display == 54
        assert res.battery_status == "2/3"
        assert res.orb_state == "ready"


@pytest.mark.asyncio
async def test_activate_jump_mocked_success() -> None:
    actuator = CockpitActuator()
    telemetry_mock = {
        "config": {
            "internalMode": 3,
            "flux": 100,
        }
    }
    jump_mock = {
        "code": 13,
        "message": "Skok udany!",
        "config": {"batteryStatus": "3/3"},
    }

    with (
        patch("httpx.AsyncClient.get") as mock_get,
        patch("httpx.AsyncClient.post") as mock_post,
    ):
        mock_get.return_value = httpx.Response(
            200,
            json=telemetry_mock,
            request=httpx.Request("GET", "https://hub.ag3nts.org/timetravel_backend"),
        )
        mock_post.return_value = httpx.Response(
            200,
            json=jump_mock,
            request=httpx.Request("POST", "https://hub.ag3nts.org/verify"),
        )

        res = await actuator.activate_jump(target_imode=3, timeout_seconds=2.0)
        assert res.success is True
        assert res.jump_code == 13
        assert res.battery_status == "3/3"
