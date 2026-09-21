from agents.adk_agent import ADKWindpowerAgent
from agents.base import BaseWindpowerAgent
from agents.langchain_agent import LangChainWindpowerAgent


def get_agent(backend: str = "langchain") -> BaseWindpowerAgent:
    """Factory returning the requested agent implementation ('langchain' or 'adk')."""
    backend_norm = backend.lower().strip()
    if backend_norm == "langchain":
        return LangChainWindpowerAgent()
    elif backend_norm == "adk":
        return ADKWindpowerAgent()
    else:
        raise ValueError(
            f"Unknown backend '{backend}'. Supported backends: 'langchain', 'adk'"
        )
