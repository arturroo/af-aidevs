import pytest
from schemas import (
    AgentResponse,
    HealthResponse,
    RunTaskRequest,
    RunTaskResponse,
    TelemetryEvent,
    CountTokensInput,
    CountTokensResponse,
    VerifySolutionInput,
    VerifySolutionResponse,
)


def test_agent_response():
    resp = AgentResponse(
        reasoning="Identified critical failure in ECCS8 coolant loop",
        answer="Completed with flag {FLG:...}",
    )
    assert resp.reasoning.startswith("Identified")
    assert "{FLG:...}" in resp.answer


def test_health_response():
    resp = HealthResponse(status="ok", service="cr-s02e03-failure", version="0.1.0")
    assert resp.status == "ok"
    assert resp.service == "cr-s02e03-failure"


def test_telemetry_event_formatting():
    ev = TelemetryEvent(
        timestamp_raw="2026-02-26 06:04:12",
        date_str="2026-02-26",
        time_str="06:04",
        severity="[CRIT]",
        component_id="ECCS8",
        description="runaway outlet temp. Protection interlock initiated reactor trip.",
        raw_line="[2026-02-26 06:04:12] [CRIT] ECCS8 runaway outlet temp. Protection interlock initiated reactor trip.",
    )
    line = ev.to_condensed_line()
    assert line == "[2026-02-26 06:04] [CRIT] ECCS8 runaway outlet temp. Protection interlock initiated reactor trip."


def test_run_task_request_and_response():
    req = RunTaskRequest(backend="langchain", max_iterations=3)
    assert req.backend == "langchain"
    assert req.max_iterations == 3

    resp = RunTaskResponse(
        status="success",
        session_id="s02e03_langchain_20260904_120000",
        flag="{FLG:MOCK_FLAG}",
        token_count=1350,
        iterations=2,
        condensed_logs_sample="sample log line",
        notes_file="run_notes.txt",
    )
    assert resp.status == "success"
    assert resp.token_count <= 1500
    assert resp.flag == "{FLG:MOCK_FLAG}"


def test_count_tokens_schemas():
    inp = CountTokensInput(reasoning="Checking candidate size", text="[2026-02-26 06:04] [CRIT] ECCS8 trip")
    assert inp.reasoning is not None

    out = CountTokensResponse(token_count=120, is_valid=True)
    assert out.is_valid is True
    assert out.token_count == 120


def test_verify_solution_schemas():
    inp = VerifySolutionInput(reasoning="Submitting to Centrala", logs="[2026-02-26 06:04] [CRIT] ECCS8 trip")
    assert inp.logs is not None

    out = VerifySolutionResponse(
        code=0,
        message="OK {FLG:TEST}",
        flag="{FLG:TEST}",
        is_success=True,
    )
    assert out.is_success is True
    assert out.flag == "{FLG:TEST}"
