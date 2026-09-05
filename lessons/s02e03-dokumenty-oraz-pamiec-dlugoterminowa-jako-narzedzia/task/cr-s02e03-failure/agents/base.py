from abc import ABC, abstractmethod
from schemas import RunTaskResponse


class BaseFailureAgent(ABC):
    """Abstract interface for autonomous failure log analysis and remediation agents."""

    @abstractmethod
    async def solve(self, session_id: str, max_iterations: int = 5) -> RunTaskResponse:
        """
        Executes end-to-end failure log download via cr-mcp-web-gateway,
        staging in cr-mcp-workspace, in-memory filtering, token budget verification,
        and iterative technician feedback remediation.
        """
        pass
