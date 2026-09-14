from abc import ABC, abstractmethod
from schemas import RunTaskResponse


class BaseFirmwareAgent(ABC):
    """Abstract base class for firmware diagnostic agents across execution backends."""

    @abstractmethod
    async def solve(self, session_id: str, max_iterations: int = 15) -> RunTaskResponse:
        """Executes the diagnostic and remediation loop to fix cooler.bin, acquire token, and retrieve flag."""
        pass
