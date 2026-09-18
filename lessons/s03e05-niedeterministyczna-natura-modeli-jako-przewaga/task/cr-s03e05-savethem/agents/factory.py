import logging
from agents.adk_agent import ADKNavigationAgent
from agents.base import BaseNavigationAgent
from agents.langchain_agent import LangChainNavigationAgent

logger = logging.getLogger("agents.factory")


def get_agent(backend: str = "langchain") -> BaseNavigationAgent:
    """Returns the requested agent implementation instance ('langchain' or 'adk')."""
    normalized = backend.lower().strip()
    if normalized == "adk":
        logger.info("Instantiating Google ADK Navigation Agent")
        return ADKNavigationAgent()
    elif normalized == "langchain":
        logger.info("Instantiating LangChain Navigation Agent")
        return LangChainNavigationAgent()
    else:
        logger.warning(
            f"Unknown backend '{backend}'. Defaulting to LangChain Navigation Agent."
        )
        return LangChainNavigationAgent()
