"""Unit tests for agent factory and execution helpers."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agents.adk_agent import ADKWindpowerAgent
from agents.factory import get_agent
from agents.langchain_agent import LangChainWindpowerAgent
from main import app, save_run_notes
from schemas import RunTaskResponse


def test_agent_factory_selection():
    agent_lc = get_agent("langchain")
    assert isinstance(agent_lc, LangChainWindpowerAgent)

    agent_adk = get_agent("adk")
    assert isinstance(agent_adk, ADKWindpowerAgent)

    with pytest.raises(ValueError):
        get_agent("unsupported_backend")


def test_health_check_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "cr-s04e02-windpower"


@pytest.mark.asyncio
async def test_save_run_notes_stores_unanonymized_flag():
    resp = RunTaskResponse(
        status="success",
        backend="langchain",
        session_id="test_run_notes_session",
        flag="{FLG:RAW_COURSE_FLAG_12345}",
        actions_taken=[
            "probe_help",
            "probe_get_documentation",
            "execute_turbine_schedule",
        ],
        reasoning="All operations completed successfully within 7.2s.",
        execution_time_seconds=7.2,
        scheduled_points_count=3,
    )

    await save_run_notes(resp)

    notes_file = Path(__file__).parent.parent / "run_notes.txt"
    assert notes_file.exists()
    content = notes_file.read_text(encoding="utf-8")

    # Assert raw unanonymized flag is preserved in private workspace run_notes.txt
    assert "{FLG:RAW_COURSE_FLAG_12345}" in content
    assert "Flag: {FLG:RAW_COURSE_FLAG_12345}" in content
    assert "Execution Time: 7.2s" in content


@pytest.mark.asyncio
async def test_run_endpoint_get_and_post():
    from unittest.mock import AsyncMock, patch

    client = TestClient(app)
    mock_response = RunTaskResponse(
        status="success",
        backend="langchain",
        session_id="test_session_get",
        flag="{FLG:test_flag_get}",
        actions_taken=["probe_help", "solve_and_execute_windpower"],
        reasoning="Test reasoning",
        execution_time_seconds=5.0,
        scheduled_points_count=2,
    )

    with patch("main.get_agent") as mock_get_agent:
        mock_agent = AsyncMock()
        mock_agent.execute.return_value = mock_response
        mock_get_agent.return_value = mock_agent

        # 1. Test GET /run with query params
        res_get = client.get(
            "/run?backend=langchain&session_id=test_session_get&max_iterations=45"
        )
        assert res_get.status_code == 200
        data_get = res_get.json()
        assert data_get["status"] == "success"
        assert data_get["flag"] == "{FLG:test_flag_get}"
        mock_agent.execute.assert_called_with(
            session_id="test_session_get", recursion_limit=45
        )

        # 2. Test POST /run with default max_iterations=30
        res_post = client.post(
            "/run", json={"backend": "adk", "session_id": "test_session_post"}
        )
        assert res_post.status_code == 200
        data_post = res_post.json()
        assert data_post["status"] == "success"
        mock_agent.execute.assert_called_with(
            session_id="test_session_post", recursion_limit=30
        )
