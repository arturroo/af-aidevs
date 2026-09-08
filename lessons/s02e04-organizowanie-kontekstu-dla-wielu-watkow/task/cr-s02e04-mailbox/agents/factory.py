import logging
from agents.base import BaseMailboxAgent
from agents.langchain_agent import LangChainMailboxAgent
from agents.adk_agent import ADKMailboxAgent

logger = logging.getLogger("agents.factory")


def create_agent(backend: str = "langchain") -> BaseMailboxAgent:
    """Factory function instantiating the requested autonomous mailbox agent backend."""
    normalized = backend.strip().lower()
    logger.info(f"Instantiating mailbox agent for backend: {normalized}")

    if normalized == "langchain":
        return LangChainMailboxAgent()
    elif normalized in ("adk", "genai", "google-adk"):
        return ADKMailboxAgent()
    else:
        raise ValueError(
            f"Unsupported backend '{backend}'. Supported backends are: 'langchain', 'adk'."
        )
