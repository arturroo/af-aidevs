from abc import ABC, abstractmethod
from schemas import RunTaskResponse


class BaseMailboxAgent(ABC):
    """Abstract base class for mailbox investigation agents across execution backends."""

    @abstractmethod
    async def solve(self, session_id: str, max_iterations: int = 10) -> RunTaskResponse:
        """Executes the autonomous mailbox investigation workflow to capture the course flag."""
        pass
