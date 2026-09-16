"""Factory module for instantiating Tool callers and Orchestrators by backend name."""

import logging
from agents.adk_agent import ADKOrchestrator, ADKToolCaller
from agents.base import TaskOrchestrator, ToolLLMCaller
from agents.langchain_agent import LangChainOrchestrator, LangChainToolCaller

logger = logging.getLogger(__name__)


def get_tool_caller(backend: str = "langchain") -> ToolLLMCaller:
    """Instantiate the tool LLM caller for the specified backend ('langchain' | 'adk')."""
    normalized = (backend or "langchain").strip().lower()
    if normalized == "adk":
        logger.info("Using Google GenAI SDK / ADK tool caller")
        return ADKToolCaller()
    logger.info("Using LangChain tool caller")
    return LangChainToolCaller()


def get_orchestrator(backend: str = "langchain") -> TaskOrchestrator:
    """Instantiate the task orchestrator for the specified backend ('langchain' | 'adk')."""
    normalized = (backend or "langchain").strip().lower()
    if normalized == "adk":
        logger.info("Using Google ADK orchestrator")
        return ADKOrchestrator()
    logger.info("Using LangChain orchestrator")
    return LangChainOrchestrator()
