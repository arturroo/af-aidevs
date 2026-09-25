from abc import ABC, abstractmethod

from schemas import RunTaskResponse


class BaseWarehouseAgent(ABC):
    """Abstract base contract for S04E05 warehouse agents (LangChain & Google ADK)."""

    @abstractmethod
    async def execute(
        self,
        session_id: str,
        recursion_limit: int | None = None,
        model: str | None = None,
        thinking_level: str | None = None,
    ) -> RunTaskResponse:
        """Executes autonomous API discovery, SQLite introspection, staging, validation, and batch dispatch."""
