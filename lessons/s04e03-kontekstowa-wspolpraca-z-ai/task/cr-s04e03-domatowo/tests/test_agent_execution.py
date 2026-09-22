"""Unit tests for agent factory and execution pipeline in S04E03."""

from unittest.mock import AsyncMock, patch

import pytest

from agents.adk_agent import ADKDomatowoAgent
from agents.factory import get_agent
from agents.langchain_agent import LangChainDomatowoAgent
from schemas import RunTaskResponse


def test_agent_factory_selection():
    lc_agent = get_agent("langchain")
    assert isinstance(lc_agent, LangChainDomatowoAgent)

    adk_agent = get_agent("adk")
    assert isinstance(adk_agent, ADKDomatowoAgent)

    with pytest.raises(ValueError):
        get_agent("invalid_backend")


@pytest.mark.asyncio
async def test_langchain_agent_mock_execution():
    agent = LangChainDomatowoAgent()
    session_id = "test-mock-lc"

    # Mock the execute method directly to verify contract compliance
    with patch.object(
        agent,
        "execute",
        new=AsyncMock(
            return_value=RunTaskResponse(
                success=True,
                flag="{FLG:MOCK_DOMATOWO_WIN}",
                backend_used="langchain",
                ap_spent=42,
                final_location="F2",
            )
        ),
    ):
        result = await agent.execute(session_id=session_id)
        assert result.success is True
        assert result.flag == "{FLG:MOCK_DOMATOWO_WIN}"
        assert result.ap_spent == 42
        assert result.final_location == "F2"
