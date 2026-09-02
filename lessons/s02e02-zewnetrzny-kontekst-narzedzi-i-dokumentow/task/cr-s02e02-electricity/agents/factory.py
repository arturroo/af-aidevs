from agents.base import BaseSolverAgent
from agents.langchain_agent import LangChainSolverAgent
from agents.adk_agent import ADKSolverAgent


class AgentFactory:
    """Factory Pattern to instantiate solver agents based on backend choice."""

    @staticmethod
    def create(backend: str = "langchain") -> BaseSolverAgent:
        normalized = backend.strip().lower()
        if normalized == "langchain":
            return LangChainSolverAgent()
        elif normalized == "adk":
            return ADKSolverAgent()
        else:
            raise ValueError(f"Unsupported backend '{backend}'. Choose 'langchain' or 'adk'.")
