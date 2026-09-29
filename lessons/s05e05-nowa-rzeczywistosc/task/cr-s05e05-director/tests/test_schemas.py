from schemas import (
    PhaseResult,
    RunTaskRequest,
    RunTaskResponse,
    StabilizationDecision,
)


def test_run_task_request_defaults() -> None:
    req = RunTaskRequest()
    assert req.model is None
    assert req.thinking_level is None
    assert req.session_id is None


def test_run_task_request_custom() -> None:
    req = RunTaskRequest(
        model="gemini-3.5-flash-lite",
        thinking_level="low",
        session_id="custom-session-123",
        max_iterations=100,
    )
    assert req.model == "gemini-3.5-flash-lite"
    assert req.thinking_level == "low"
    assert req.session_id == "custom-session-123"
    assert req.max_iterations == 100


def test_phase_result_schema() -> None:
    res = PhaseResult(
        phase=1,
        target="2238-11-05",
        status="COMPLETED",
        battery="3/3",
        details="Jump successful",
    )
    assert res.phase == 1
    assert res.target == "2238-11-05"
    assert res.status == "COMPLETED"


def test_run_task_response_schema() -> None:
    resp = RunTaskResponse(
        success=True,
        session_id="sess-1",
        flag="{FLG:CHRONOS_SUCCESS}",
        execution_time_seconds=12.34,
        phases_completed=[
            PhaseResult(
                phase=1,
                target="2238-11-05",
                status="COMPLETED",
                battery="3/3",
            ),
            PhaseResult(
                phase=2,
                target="2026-09-29",
                status="COMPLETED",
                battery="2/3",
            ),
            PhaseResult(
                phase=3,
                target="2024-11-12",
                status="COMPLETED",
                battery="0/3",
            ),
        ],
        message="Mission complete",
    )
    assert resp.success is True
    assert len(resp.phases_completed) == 3
    assert resp.flag == "{FLG:CHRONOS_SUCCESS}"


def test_stabilization_decision_schema() -> None:
    dec = StabilizationDecision(
        stabilization_value="0",
        reasoning="Nominal conditions",
    )
    assert dec.stabilization_value == "0"
