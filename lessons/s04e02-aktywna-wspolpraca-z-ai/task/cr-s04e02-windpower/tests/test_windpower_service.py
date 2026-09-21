from unittest.mock import AsyncMock

import pytest

from services.windpower_service import WindpowerService


def test_normalize_weather_list_format():
    svc = WindpowerService(mcp_service=AsyncMock(), audit_service=AsyncMock())
    raw_payload = {
        "weather": [
            {"date": "2026-03-24", "hour": "18:00:00", "wind": 18.2},
            {"startDate": "2026-03-24", "startHour": "19:00", "windMs": 22.1},
            {"date": "2026-03-24", "hour": "20", "speed": 10.5},
        ]
    }
    normalized = svc._normalize_weather(raw_payload)
    assert len(normalized) == 3
    assert normalized[0] == {
        "startDate": "2026-03-24",
        "startHour": "18:00:00",
        "windMs": 18.2,
    }
    assert normalized[1] == {
        "startDate": "2026-03-24",
        "startHour": "19:00:00",
        "windMs": 22.1,
    }
    assert normalized[2] == {
        "startDate": "2026-03-24",
        "startHour": "20:00:00",
        "windMs": 10.5,
    }


def test_normalize_weather_dict_format():
    svc = WindpowerService(mcp_service=AsyncMock(), audit_service=AsyncMock())
    raw_payload = {
        "forecast": {
            "2026-03-24 16:00:00": 7.5,
            "2026-03-24 17:00:00": 19.8,
        }
    }
    normalized = svc._normalize_weather(raw_payload)
    assert len(normalized) == 2
    assert normalized[0]["startHour"] == "16:00:00"
    assert normalized[0]["windMs"] == 7.5
    assert normalized[1]["windMs"] == 19.8


def test_match_unlock_code():
    svc = WindpowerService(mcp_service=AsyncMock(), audit_service=AsyncMock())
    point = {
        "startDate": "2026-03-24",
        "startHour": "18:00:00",
        "windMs": 22.0,
        "pitchAngle": 90,
    }
    codes = [
        {"startDate": "2026-03-24", "startHour": "17:00:00", "unlockCode": "sig_17"},
        {"startDate": "2026-03-24", "startHour": "18:00:00", "unlockCode": "sig_18"},
    ]
    matched = svc._match_unlock_code(point, codes)
    assert matched == "sig_18"

    # Test with Centrala's signedParams structure
    point2 = {
        "startDate": "2026-09-22",
        "startHour": "20:00:00",
        "windMs": 6.6,
        "pitchAngle": 0,
    }
    codes_signed_params = [
        {
            "code": 12,
            "sourceFunction": "unlockCodeGenerator",
            "unlockCode": "storm_sig",
            "signedParams": {
                "startDate": "2026-09-22",
                "startHour": "18:00:00",
                "windMs": "25.0",
                "pitchAngle": "90.0",
            },
        },
        {
            "code": 12,
            "sourceFunction": "unlockCodeGenerator",
            "unlockCode": "prod_sig",
            "signedParams": {
                "startDate": "2026-09-22",
                "startHour": "20:00:00",
                "windMs": "6.6",
                "pitchAngle": "0.0",
            },
        },
    ]
    matched2 = svc._match_unlock_code(point2, codes_signed_params)
    assert matched2 == "prod_sig"


@pytest.mark.asyncio
async def test_solve_and_execute_schedule_flow():
    mock_mcp = AsyncMock()
    mock_audit = AsyncMock()

    call_count = 0

    # Define mock responses for sequential calls to post_web_resource
    async def mock_post(session_id: str, url: str, payload: dict):
        nonlocal call_count
        answer = payload.get("answer", {})
        action = answer.get("action")
        param = answer.get("param")

        if action == "start":
            return {"code": 0, "message": "Service window active"}
        elif action == "get":
            return {"code": 0, "message": f"Queued {param}"}
        elif action == "getResult":
            # Simulate returning queued reports
            call_count += 1

            if call_count == 1:
                return {
                    "sourceFunction": "weather",
                    "weather": [
                        {
                            "startDate": "2026-03-24",
                            "startHour": "18:00:00",
                            "windMs": 19.5,
                        },
                        {
                            "startDate": "2026-03-24",
                            "startHour": "19:00:00",
                            "windMs": 21.0,
                        },
                        {
                            "startDate": "2026-03-24",
                            "startHour": "20:00:00",
                            "windMs": 8.0,
                        },
                    ],
                }
            elif call_count == 2:
                return {
                    "sourceFunction": "powerplantcheck",
                    "data": {"deficit": 1000},
                }
            elif call_count == 3:
                return {
                    "sourceFunction": "turbinecheck",
                    "data": {"status": "ok"},
                }
            else:
                # Unlock code responses
                return {
                    "sourceFunction": "unlockCodeGenerator",
                    "unlockCode": f"mock_sig_{call_count}",
                }
        elif action == "unlockCodeGenerator":
            return {"code": 0, "message": "Queued unlockCodeGenerator"}
        elif action == "config":
            return {"code": 0, "message": "Configuration accepted"}
        elif action == "done":
            return {"code": 0, "message": "Task complete: {FLG:turbine_energy_secured}"}

        return {"code": 0, "message": "ok"}

    mock_mcp.post_web_resource.side_effect = mock_post

    svc = WindpowerService(mcp_service=mock_mcp, audit_service=mock_audit)
    res = await svc.solve_and_execute_schedule(
        session_id="test_session",
        max_safe_wind_speed=15.0,
        feathering_pitch_angle=90,
        production_pitch_angle=45,
    )

    assert res.status == "success"
    assert res.flag == "{FLG:turbine_energy_secured}"
    assert res.execution_time_seconds < 40.0
    # Should configure 2 storm hours (18:00 and 19:00) + 1 production hour (20:00)
    assert len(res.scheduled_points) == 3
    # Check storm hours
    storm_points = [p for p in res.scheduled_points if p["pitchAngle"] == 90]
    prod_points = [p for p in res.scheduled_points if p["pitchAngle"] == 45]
    assert len(storm_points) == 2
    assert len(prod_points) == 1
    assert prod_points[0]["turbineMode"] == "production"


@pytest.mark.asyncio
async def test_execute_schedule_flow():
    from schemas import TurbineConfigPoint

    mock_mcp = AsyncMock()
    mock_audit = AsyncMock()

    call_count = 0

    async def mock_post(session_id: str, url: str, payload: dict):
        nonlocal call_count
        answer = payload.get("answer", {})
        action = answer.get("action")

        if action == "start":
            return {"code": 0, "message": "Service window active"}
        elif action == "get":
            return {"code": 0, "message": "Queued turbinecheck"}
        elif action == "getResult":
            call_count += 1
            return {
                "sourceFunction": "unlockCodeGenerator",
                "unlockCode": f"sig_{call_count}",
            }
        elif action == "unlockCodeGenerator":
            return {"code": 0, "message": "Queued unlockCodeGenerator"}
        elif action == "config":
            return {"code": 0, "message": "Configuration accepted"}
        elif action == "done":
            return {"code": 0, "message": "Task complete: {FLG:turbine_direct_success}"}

        return {"code": 0, "message": "ok"}

    mock_mcp.post_web_resource.side_effect = mock_post

    svc = WindpowerService(mcp_service=mock_mcp, audit_service=mock_audit)
    svc.cached_weather = {
        "weather": [
            {"startDate": "2026-03-24", "startHour": "18:00:00", "windMs": 19.5},
            {"startDate": "2026-03-24", "startHour": "20:00:00", "windMs": 8.0},
        ]
    }
    svc.cached_powerplant = {"deficitMwh": 0.015}
    svc.cached_turbinecheck = {"status": "ok"}

    configs = [
        TurbineConfigPoint(
            startDate="2026-03-24",
            startHour="18:00:00",
            windMs=19.5,
            pitchAngle=90,
            turbineMode="idle",
        ),
        TurbineConfigPoint(
            startDate="2026-03-24",
            startHour="20:00:00",
            windMs=8.0,
            pitchAngle=0,
            turbineMode="production",
        ),
    ]
    res = await svc.execute_schedule(
        session_id="test_exec_session",
        configs=configs,
        reasoning="Executing validated schedule",
    )

    assert res.status == "success"
    assert res.flag == "{FLG:turbine_direct_success}"
    assert len(res.scheduled_points) == 2
    assert res.execution_time_seconds < 40.0
