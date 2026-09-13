from abc import ABC, abstractmethod
from schemas import RunTaskResponse


class BaseEvaluator(ABC):
    """Abstract base class for industrial sensor evaluation pipeline runners."""

    @abstractmethod
    async def run(self, session_id: str) -> RunTaskResponse:
        """Executes full audit pipeline: ingest, physical audit, semantic classification, submission."""
        pass
