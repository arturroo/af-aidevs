import logging
from agents.base import BaseFirmwareAgent
from agents.langchain_agent import LangChainFirmwareAgent
from agents.adk_agent import ADKFirmwareAgent

logger = logging.getLogger("agents.factory")


def create_agent(backend: str = "langchain") -> BaseFirmwareAgent:
    """Factory function instantiating the requested firmware diagnostic agent backend."""
    normalized = backend.strip().lower()
    logger.info(f"Instantiating firmware diagnostic agent for backend: {normalized}")

    if normalized == "langchain":
        return LangChainFirmwareAgent()
    elif normalized in ("adk", "google-adk"):
        return ADKFirmwareAgent()
    else:
        raise ValueError(
            f"Unsupported backend '{backend}'. Supported backends are: 'langchain', 'adk'."
        )
