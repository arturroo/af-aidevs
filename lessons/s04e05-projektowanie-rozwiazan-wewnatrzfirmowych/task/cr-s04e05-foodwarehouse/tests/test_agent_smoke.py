from agents.adk_agent import ADKWarehouseAgent
from agents.factory import get_agent
from agents.langchain_agent import LangChainWarehouseAgent


def test_agent_factory_returns_expected_types():
    """Verify that factory creates correct agent instances with populated system prompts."""
    langchain_agent = get_agent("langchain")
    assert isinstance(langchain_agent, LangChainWarehouseAgent)
    assert langchain_agent.prompt_config.system_prompt
    assert len(langchain_agent.prompt_config.system_prompt) > 50

    adk_agent = get_agent("adk")
    assert isinstance(adk_agent, ADKWarehouseAgent)
    assert adk_agent.prompt_config.system_prompt
    assert len(adk_agent.prompt_config.system_prompt) > 50


def test_langchain_agent_wireup_smoke():
    """Verify that LangChain agent tools and create_agent wire up without argument errors."""
    agent = get_agent("langchain")
    session_id = "smoke-test-session"
    state_tracker = {
        "actions_taken": [],
        "discovery_queries": 0,
        "signatures_generated": 0,
        "orders_created": 0,
        "items_appended": 0,
        "flag": None,
    }
    tools = agent._create_tools(session_id, state_tracker)
    assert len(tools) == 6

    # Verify that create_agent wires up with model, tools, and system_prompt
    from langchain.agents import create_agent

    runnable_agent = create_agent(
        model=agent.llm,
        tools=tools,
        system_prompt=agent.prompt_config.system_prompt,
    )
    assert runnable_agent is not None


def test_adk_agent_wireup_smoke():
    """Verify that Google ADK agent and runner wire up without argument errors."""
    agent = get_agent("adk")
    session_id = "smoke-test-session"
    state_tracker = {
        "actions_taken": [],
        "discovery_queries": 0,
        "signatures_generated": 0,
        "orders_created": 0,
        "items_appended": 0,
        "flag": None,
    }
    tools = agent._create_tools(session_id, state_tracker)
    assert len(tools) == 6

    from google.adk import Agent, Runner
    from google.adk.sessions import InMemorySessionService

    adk_core_agent = Agent(
        name="adk_warehouse_agent",
        model=agent.prompt_config.model or "gemini-3.8-flash",
        instruction=agent.prompt_config.system_prompt,
        tools=tools,
    )
    assert adk_core_agent is not None

    session_service = InMemorySessionService()
    runner = Runner(
        agent=adk_core_agent,
        app_name="smoke_test_app",
        session_service=session_service,
    )
    assert runner is not None
