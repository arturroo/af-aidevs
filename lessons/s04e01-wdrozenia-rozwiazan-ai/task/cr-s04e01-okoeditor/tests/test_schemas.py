"""Unit tests for Pydantic schemas in cr-s04e01-okoeditor."""

import pytest
from pydantic import ValidationError

from schemas import (
    AgentResponse,
    CallOkoApiInput,
    CallOkoApiResponse,
    HealthResponse,
    RunTaskRequest,
    RunTaskResponse,
)


def test_health_response():
    hr = HealthResponse(timestamp="2026-09-18T22:00:00Z")
    assert hr.status == "healthy"
    assert hr.service == "cr-s04e01-okoeditor"
    assert hr.timestamp == "2026-09-18T22:00:00Z"


def test_run_task_request():
    req = RunTaskRequest()
    assert req.backend == "langchain"
    assert req.session_id is None

    req_adk = RunTaskRequest(backend="adk", session_id="custom_123")
    assert req_adk.backend == "adk"
    assert req_adk.session_id == "custom_123"

    with pytest.raises(ValidationError):
        RunTaskRequest(backend="unsupported_framework")


def test_run_task_response():
    resp = RunTaskResponse(
        status="success",
        backend="langchain",
        session_id="s04e01_langchain_123",
        flag="{FLG:TEST_OKO}",
        actions_taken=["help", "update_report", "done"],
        reasoning="All 3 operations succeeded.",
    )
    assert resp.status == "success"
    assert resp.flag == "{FLG:TEST_OKO}"
    assert len(resp.actions_taken) == 3


def test_call_oko_api_input_requires_reasoning():
    # Without reasoning should fail validation
    with pytest.raises(ValidationError):
        CallOkoApiInput(action="help")

    # With reasoning should succeed
    valid = CallOkoApiInput(action="help", reasoning="Inspect API schema")
    assert valid.action == "help"
    assert valid.reasoning == "Inspect API schema"
    assert valid.params is None

    with_params = CallOkoApiInput(
        action="update_report",
        params={"id": "skolwin_1", "category": "animals"},
        reasoning="Reclassifying to wildlife",
    )
    assert with_params.params == {"id": "skolwin_1", "category": "animals"}


def test_call_oko_api_response():
    resp = CallOkoApiResponse(
        status="success",
        action="help",
        code=0,
        message="Available commands...",
        data={"commands": ["help", "done"]},
        hint="Next step: query reports",
    )
    assert resp.code == 0
    assert resp.status == "success"
    assert resp.hint == "Next step: query reports"


def test_agent_response():
    ar = AgentResponse(
        reasoning="Step 1, 2, 3 complete",
        flag="{FLG:TEST_FLAG}",
        actions_taken=["help", "done"],
        summary="Mission accomplished",
    )
    assert ar.flag == "{FLG:TEST_FLAG}"
    assert len(ar.actions_taken) == 2
