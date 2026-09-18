from agents.adk_agent import ADKOkoAgent
from agents.base import BaseOkoAgent
from agents.langchain_agent import LangChainOkoAgent


def get_agent(backend: str = "langchain") -> BaseOkoAgent:
    """Factory returning the requested agent implementation ('langchain' or 'adk')."""
    backend_norm = backend.lower().strip()
    if backend_norm == "langchain":
        return LangChainOkoAgent()
    elif backend_norm == "adk":
        return ADKOkoAgent()
    else:
        raise ValueError(
            f"Unknown backend '{backend}'. Supported backends: 'langchain', 'adk'"
        )
