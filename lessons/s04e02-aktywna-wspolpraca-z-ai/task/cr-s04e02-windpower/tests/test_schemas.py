import pytest
from pydantic import ValidationError

from schemas import (
    HealthResponse,
    ProbeWindpowerApiInput,
    ProbeWindpowerApiResponse,
    RunTaskRequest,
    RunTaskResponse,
    SaveDiscoveryNotesInput,
    SolveAndExecuteResponse,
)


def test_health_response_defaults():
    resp = HealthResponse(timestamp="2026-09-20T22:00:00+02:00")
    assert resp.status == "healthy"
    assert resp.service == "cr-s04e02-windpower"
    assert resp.timestamp == "2026-09-20T22:00:00+02:00"


def test_run_task_request_validation():
    req = RunTaskRequest(backend="langchain")
    assert req.backend == "langchain"
    assert req.max_iterations == 30

    req_adk = RunTaskRequest(backend="adk", recursion_limit=45)
    assert req_adk.backend == "adk"
    assert req_adk.max_iterations == 45

    req_alias = RunTaskRequest(recursion=50)
    assert req_alias.max_iterations == 50

    with pytest.raises(ValidationError):
        RunTaskRequest(backend="invalid_backend")  # type: ignore

    with pytest.raises(ValidationError):
        RunTaskRequest(max_iterations=101)


def test_run_task_response_coercion():
    resp = RunTaskResponse(
        status="success",
        backend="langchain",
        session_id="test_session",
        flag="{FLG:test_flag}",
        actions_taken=["help", "solve_and_execute_windpower"],
        reasoning=[{"text": "Line 1"}, {"text": "Line 2"}],
        execution_time_seconds=6.5,
        scheduled_points_count=3,
    )
    assert resp.reasoning == "Line 1\nLine 2"
    assert resp.scheduled_points_count == 3
    assert resp.execution_time_seconds == 6.5


def test_probe_windpower_api_input():
    probe_in = ProbeWindpowerApiInput(
        action="help",
        reasoning="Discovering API functions in Phase 1",
    )
    assert probe_in.action == "help"
    assert probe_in.params is None

    with pytest.raises(ValidationError):
        # reasoning is mandatory
        ProbeWindpowerApiInput(action="help")  # type: ignore


def test_probe_windpower_api_response():
    resp = ProbeWindpowerApiResponse(
        status="success",
        action="help",
        code=13,
        message="Windpower API help",
        data={"actions": {"start": {}}},
    )
    assert resp.status == "success"
    assert resp.code == 13


def test_save_discovery_notes_input():
    notes_in = SaveDiscoveryNotesInput(
        file_path="specs.md",
        notes_content="# Turbine Specs\n- safe_wind: 15.0",
        reasoning="Saving discovered specifications for solver phase",
    )
    assert notes_in.file_path == "specs.md"
    assert "safe_wind: 15.0" in notes_in.notes_content


def test_solve_and_execute_response():
    resp = SolveAndExecuteResponse(
        status="success",
        code=0,
        message="{FLG:turbine_energy_secured}",
        flag="{FLG:turbine_energy_secured}",
        scheduled_points=[
            {
                "timestamp": "2026-03-24 18:00:00",
                "pitchAngle": 90,
                "turbineMode": "idle",
                "unlockCode": "sig123",
            }
        ],
        execution_time_seconds=7.8,
    )
    assert resp.flag == "{FLG:turbine_energy_secured}"
    assert len(resp.scheduled_points) == 1
    assert resp.execution_time_seconds < 40.0


def test_turbine_config_point_validation():
    from schemas import TurbineConfigPoint

    # Test hour formatting validation
    pt = TurbineConfigPoint(
        startDate="2026-03-24",
        startHour="18",
        windMs=19.5,
        pitchAngle=90,
        turbineMode="idle",
    )
    assert pt.startHour == "18:00:00"

    pt_colon = TurbineConfigPoint(
        startDate="2026-03-24",
        startHour="8:30:15",
        windMs=10.0,
        pitchAngle=0,
        turbineMode="production",
    )
    assert pt_colon.startHour == "08:00:00"


def test_execute_turbine_schedule_input():
    from schemas import ExecuteTurbineScheduleInput, TurbineConfigPoint

    inp = ExecuteTurbineScheduleInput(
        reasoning="Testing turbine schedule input",
        configs=[
            TurbineConfigPoint(
                startDate="2026-03-24",
                startHour="18:00:00",
                windMs=19.5,
                pitchAngle=90,
                turbineMode="idle",
            )
        ],
    )
    assert len(inp.configs) == 1
    assert inp.configs[0].pitchAngle == 90
