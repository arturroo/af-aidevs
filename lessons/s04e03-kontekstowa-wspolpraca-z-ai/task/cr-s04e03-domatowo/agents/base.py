from abc import ABC, abstractmethod

from schemas import RunTaskResponse


class BaseDomatowoAgent(ABC):
    """Abstract base contract for Domatowo rescue agents (LangChain & Google ADK)."""

    @abstractmethod
    async def execute(
        self, session_id: str, recursion_limit: int = 30
    ) -> RunTaskResponse:
        """Executes autonomous API discovery, tactical search, and helicopter evacuation."""
