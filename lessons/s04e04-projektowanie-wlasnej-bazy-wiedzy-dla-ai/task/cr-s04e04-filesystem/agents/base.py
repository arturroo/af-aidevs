from abc import ABC, abstractmethod

from schemas import RunTaskResponse


class BaseFilesystemAgent(ABC):
    """Abstract base contract for S04E04 filesystem agents (LangChain & Google ADK)."""

    @abstractmethod
    async def execute(
        self, session_id: str, recursion_limit: int = 30
    ) -> RunTaskResponse:
        """Executes autonomous notes extraction, workspace staging, validation, and batch push."""
