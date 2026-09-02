from typing import Protocol
from schemas import SolverResult


class BaseSolverAgent(Protocol):
    """Base interface for dual-backend solver agents (LangChain and ADK)."""

    async def solve(self, session_id: str) -> SolverResult:
        """Executes the autonomous agentic workflow to solve the puzzle."""
        ...
