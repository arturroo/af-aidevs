import pytest
from pydantic import ValidationError
from schemas import (
    DamCoordinates,
    DroneInstructionsSubmission,
    DroneVerificationResponse,
    DroneMissionResult,
    RunTaskRequest,
    RunTaskResponse,
    HealthResponse,
)


def test_dam_coordinates_valid():
    coords = DamCoordinates(
        total_columns=10,
        total_rows=10,
        dam_column=3,
        dam_row=7,
        visual_evidence="Darker blue saturation at col 3, row 7 near concrete barrier",
        reasoning="Counted 10x10 sectors. Dam is clearly identifiable at (3, 7).",
    )
    assert coords.dam_column == 3
    assert coords.dam_row == 7
    assert coords.total_columns == 10
    assert coords.total_rows == 10


def test_dam_coordinates_invalid_bounds():
    with pytest.raises(ValidationError):
        DamCoordinates(
            total_columns=0,  # ge=1 violated
            total_rows=10,
            dam_column=-1,   # ge=1 violated
            dam_row=7,
            visual_evidence="Invalid",
            reasoning="Invalid",
        )


def test_drone_instructions_submission_valid():
    submission = DroneInstructionsSubmission(
        instructions=["start", "setTarget PWR6132PL", "flyTo 3,7", "detonate"],
        reasoning="Official mission registers target power plant, while route detonates dam.",
    )
    assert len(submission.instructions) == 4
    assert "start" in submission.instructions


def test_drone_instructions_submission_empty_fails():
    with pytest.raises(ValidationError):
        DroneInstructionsSubmission(
            instructions=[],  # min_length=1 violated
            reasoning="Empty test",
        )


def test_drone_verification_response():
    resp = DroneVerificationResponse(
        code=0,
        message="OK {FLG:CONFIRMED_STRIKE_SUCCESS}",
        flag="{FLG:CONFIRMED_STRIKE_SUCCESS}",
        is_success=True,
    )
    assert resp.is_success is True
    assert resp.flag == "{FLG:CONFIRMED_STRIKE_SUCCESS}"


def test_run_task_models():
    req = RunTaskRequest(backend="langchain", max_iterations=5)
    assert req.backend == "langchain"
    assert req.max_iterations == 5

    res = RunTaskResponse(
        status="success",
        session_id="s02e05_langchain_20260910_120000",
        backend="langchain",
        flag="{FLG:SAMPLE}",
        iterations=2,
        instructions=["start", "flyTo 3,7"],
        summary="Completed",
    )
    assert res.status == "success"
    assert res.iterations == 2


def test_health_response():
    h = HealthResponse(status="ok", service="cr-s02e05-drone", version="0.1.0")
    assert h.status == "ok"
