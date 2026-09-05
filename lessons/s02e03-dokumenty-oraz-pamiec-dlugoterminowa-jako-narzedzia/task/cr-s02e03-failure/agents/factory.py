import logging
from agents.langchain_agent import LangChainFailureAgent
from agents.adk_agent import ADKFailureAgent

logger = logging.getLogger("agents.factory")


def get_agent(backend: str = "langchain"):
    """Instantiates and returns the appropriate agent implementation based on backend choice."""
    if backend == "genai":
        logger.info("Initializing Google GenAI SDK agent backend")
        return ADKFailureAgent()
    elif backend == "langchain":
        logger.info("Initializing LangChain 1.2.15 agent backend")
        return LangChainFailureAgent()
    else:
        logger.warning(f"Unknown backend '{backend}'. Defaulting to LangChain.")
        return LangChainFailureAgent()
