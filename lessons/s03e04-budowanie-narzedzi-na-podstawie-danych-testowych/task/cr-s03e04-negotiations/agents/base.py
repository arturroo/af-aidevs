"""Base interfaces and protocols for LLM invocations and task orchestration."""

from typing import Protocol
from schemas import (
    Tool1PostFlightInput,
    Tool1PostFlightOutput,
    Tool1PreFlightOutput,
    Tool2PreFlightOutput,
)


class ToolLLMCaller(Protocol):
    """Protocol for direct structured LLM calls powering tool endpoints."""

    async def extract_catalog_intent(self, user_query: str) -> Tool1PreFlightOutput:
        """Extract item technical entities from free-form user query."""
        ...

    async def synthesize_catalog_response(
        self, post_input: Tool1PostFlightInput
    ) -> Tool1PostFlightOutput:
        """Synthesize concise recommendation with item codes <= 500 bytes."""
        ...

    async def extract_item_codes(self, user_query: str) -> Tool2PreFlightOutput:
        """Extract 6-character item codes from user query."""
        ...


class TaskOrchestrator(Protocol):
    """Protocol for task orchestration and Centrala verification."""

    async def solve(self, session_id: str) -> dict:
        """Run task lifecycle, coordinate tool endpoints, and verify with Centrala."""
        ...
