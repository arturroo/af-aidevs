import logging
from agents.base import BaseDroneAgent
from agents.langchain_agent import LangChainDroneAgent
from agents.adk_agent import ADKDroneAgent

logger = logging.getLogger("agents.factory")


def create_agent(backend: str = "langchain") -> BaseDroneAgent:
    """Factory function instantiating the requested autonomous drone agent backend."""
    normalized = backend.strip().lower()
    logger.info(f"Instantiating drone agent for backend: {normalized}")

    if normalized == "langchain":
        return LangChainDroneAgent()
    elif normalized in ("adk", "genai", "google-adk"):
        return ADKDroneAgent()
    else:
        raise ValueError(
            f"Unsupported backend '{backend}'. Supported backends are: 'langchain', 'adk'."
        )
