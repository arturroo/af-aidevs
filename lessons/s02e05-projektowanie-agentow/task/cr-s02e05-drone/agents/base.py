from abc import ABC, abstractmethod
from schemas import RunTaskResponse


class BaseDroneAgent(ABC):
    """Abstract base class for drone strike agents across execution backends."""

    @abstractmethod
    async def solve(self, session_id: str, max_iterations: int = 10) -> RunTaskResponse:
        """Executes the autonomous drone mission workflow to formulate flight commands and capture the flag."""
        pass
