import logging
from agents.base import BaseReactorAgent

logger = logging.getLogger("agents.factory")


def create_agent(backend: str = "langchain") -> BaseReactorAgent:
    """Factory creating the appropriate reactor navigation agent backend."""
    normalized_backend = backend.strip().lower()

    if normalized_backend == "langchain":
        from agents.langchain_agent import LangChainReactorAgent

        logger.info("Instantiating LangChain 1.2.15 Reactor Agent")
        return LangChainReactorAgent()
    elif normalized_backend == "adk":
        from agents.adk_agent import ADKReactorAgent

        logger.info("Instantiating Google ADK 1.33.0 Reactor Agent")
        return ADKReactorAgent()
    else:
        raise ValueError(
            f"Unsupported agent backend '{backend}'. Supported: 'langchain', 'adk'."
        )
