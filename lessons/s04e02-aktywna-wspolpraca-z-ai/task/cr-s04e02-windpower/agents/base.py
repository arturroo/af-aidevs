from abc import ABC, abstractmethod

from schemas import RunTaskResponse


class BaseWindpowerAgent(ABC):
    """Abstract base contract for windpower agents (LangChain & Google ADK)."""

    @abstractmethod
    async def execute(
        self, session_id: str, recursion_limit: int = 30
    ) -> RunTaskResponse:
        """Executes autonomous API discovery, schedule optimization, and verification."""
