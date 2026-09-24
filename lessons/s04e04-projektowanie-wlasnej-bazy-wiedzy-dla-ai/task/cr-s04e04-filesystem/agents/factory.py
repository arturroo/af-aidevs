from agents.adk_agent import ADKFilesystemAgent
from agents.base import BaseFilesystemAgent
from agents.langchain_agent import LangChainFilesystemAgent


def get_agent(backend: str = "langchain") -> BaseFilesystemAgent:
    """Factory returning the requested agent implementation ('langchain' or 'adk')."""
    backend_norm = backend.lower().strip()
    if backend_norm == "langchain":
        return LangChainFilesystemAgent()
    elif backend_norm == "adk":
        return ADKFilesystemAgent()
    else:
        raise ValueError(
            f"Unknown backend '{backend}'. Supported backends: 'langchain', 'adk'"
        )
