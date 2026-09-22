from agents.adk_agent import ADKDomatowoAgent
from agents.base import BaseDomatowoAgent
from agents.langchain_agent import LangChainDomatowoAgent


def get_agent(backend: str = "langchain") -> BaseDomatowoAgent:
    """Factory returning the requested agent implementation ('langchain' or 'adk')."""
    backend_norm = backend.lower().strip()
    if backend_norm == "langchain":
        return LangChainDomatowoAgent()
    elif backend_norm == "adk":
        return ADKDomatowoAgent()
    else:
        raise ValueError(
            f"Unknown backend '{backend}'. Supported backends: 'langchain', 'adk'"
        )
