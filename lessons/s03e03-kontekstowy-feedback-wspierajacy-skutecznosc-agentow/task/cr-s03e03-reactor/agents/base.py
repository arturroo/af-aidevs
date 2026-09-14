from abc import ABC, abstractmethod
from schemas import RunTaskResponse


class BaseReactorAgent(ABC):
    """Abstract interface for autonomous reactor navigation agents."""

    @abstractmethod
    async def solve(
        self, session_id: str, max_iterations: int = 25
    ) -> RunTaskResponse:
        """Executes the autonomous navigation mission to slot G and captures the course flag."""
        pass
