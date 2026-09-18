from abc import ABC, abstractmethod
from schemas import RunTaskResponse


class BaseNavigationAgent(ABC):
    """Abstract base contract for navigation agents (LangChain & Google ADK)."""

    @abstractmethod
    async def execute(
        self, session_id: str, force_refresh: bool = False
    ) -> RunTaskResponse:
        """Executes autonomous tool discovery, pathfinding, and verification."""
        pass
