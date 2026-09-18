from abc import ABC, abstractmethod

from schemas import RunTaskResponse


class BaseOkoAgent(ABC):
    """Abstract base contract for OKO covert manipulation agents (LangChain & Google ADK)."""

    @abstractmethod
    async def execute(
        self, session_id: str, recursion_limit: int = 30
    ) -> RunTaskResponse:
        """Executes autonomous API introspection, 3 mutations, and verification."""
