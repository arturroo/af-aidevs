"""Unit tests for agent factory and execution helpers."""

from pathlib import Path

import pytest

from agents.adk_agent import ADKOkoAgent
from agents.factory import get_agent
from agents.langchain_agent import LangChainOkoAgent
from main import save_run_notes
from schemas import RunTaskResponse


def test_agent_factory_selection():
    agent_lc = get_agent("langchain")
    assert isinstance(agent_lc, LangChainOkoAgent)

    agent_adk = get_agent("adk")
    assert isinstance(agent_adk, ADKOkoAgent)

    with pytest.raises(ValueError):
        get_agent("unsupported_backend")


def test_save_run_notes_stores_unanonymized_flag():
    resp = RunTaskResponse(
        status="success",
        backend="langchain",
        session_id="test_run_notes_session",
        flag="{FLG:RAW_COURSE_FLAG_12345}",
        actions_taken=[
            "help",
            "update_report",
            "update_task",
            "create_incident",
            "done",
        ],
        reasoning="All operations completed successfully.",
    )

    save_run_notes(resp)

    notes_file = Path(__file__).parent.parent / "run_notes.txt"
    assert notes_file.exists()
    content = notes_file.read_text(encoding="utf-8")

    # Assert raw unanonymized flag is preserved in private workspace run_notes.txt
    assert "{FLG:RAW_COURSE_FLAG_12345}" in content
    assert "Flag: {FLG:RAW_COURSE_FLAG_12345}" in content
    assert "Backend: langchain" in content
    assert "Status: SUCCESS" in content
    assert "update_report" in content
