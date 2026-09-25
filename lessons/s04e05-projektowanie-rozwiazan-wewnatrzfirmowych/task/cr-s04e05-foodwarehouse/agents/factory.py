from agents.adk_agent import ADKWarehouseAgent
from agents.base import BaseWarehouseAgent
from agents.langchain_agent import LangChainWarehouseAgent


def get_agent(
    backend: str = "langchain",
    model: str | None = None,
    thinking_level: str | None = None,
) -> BaseWarehouseAgent:
    """Factory returning the requested agent implementation ('langchain' or 'adk')."""
    backend_norm = backend.lower().strip()
    if backend_norm == "langchain":
        return LangChainWarehouseAgent(model=model, thinking_level=thinking_level)
    elif backend_norm == "adk":
        return ADKWarehouseAgent(model=model, thinking_level=thinking_level)
    else:
        raise ValueError(
            f"Unknown backend '{backend}'. Supported backends: 'langchain', 'adk'"
        )
