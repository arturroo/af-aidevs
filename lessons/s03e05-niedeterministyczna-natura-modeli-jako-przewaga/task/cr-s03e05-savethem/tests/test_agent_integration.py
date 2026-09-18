"""Integration and smoke tests for cr-s03e05-savethem."""

import pytest
from fastapi.testclient import TestClient
from agents.factory import get_agent
from agents.langchain_agent import LangChainNavigationAgent
from agents.adk_agent import ADKNavigationAgent
from main import app


def test_agent_factory():
    lc_agent = get_agent("langchain")
    assert isinstance(lc_agent, LangChainNavigationAgent)

    adk_agent = get_agent("adk")
    assert isinstance(adk_agent, ADKNavigationAgent)


def test_health_endpoints():
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "cr-s03e05-savethem"

    # Verify root endpoint mirrors health
    res_root = client.get("/")
    assert res_root.status_code == 200
    data_root = res_root.json()
    assert data_root["status"] == "healthy"
    assert data_root["service"] == "cr-s03e05-savethem"
    assert "timestamp" in data_root
