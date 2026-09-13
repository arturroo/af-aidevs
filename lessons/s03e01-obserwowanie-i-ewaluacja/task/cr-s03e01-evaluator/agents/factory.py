import logging
from agents.base import BaseEvaluator
from agents.langchain_agent import LangChainEvaluator
from agents.genai_agent import GenAIEvaluator

logger = logging.getLogger("agents.factory")


def create_evaluator(backend: str = "langchain") -> BaseEvaluator:
    """Factory creating the appropriate telemetry evaluator runner."""
    normalized = backend.strip().lower()
    logger.info(f"Instantiating evaluator pipeline for backend: {normalized}")

    if normalized == "langchain":
        return LangChainEvaluator()
    elif normalized in ("genai", "adk", "google-adk"):
        return GenAIEvaluator()
    else:
        raise ValueError(
            f"Unsupported backend '{backend}'. Supported backends: 'langchain', 'genai'."
        )
