from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel, Field

T = TypeVar("T")


class AgentResponseEnvelope(BaseModel, Generic[T]):
    """Universal envelope following Google AIP and Pydantic v2 Generic patterns."""

    status: str = Field(
        description="Operation status: 'success' or 'error'",
        json_schema_extra={"example": "success"},
    )
    reasoning: str = Field(
        description="Mandatory audit trail justification explaining the agent's decision",
        json_schema_extra={"example": "All 9 tiles inspected and rotation steps computed."},
    )
    data: Optional[T] = Field(
        default=None,
        description="Typed payload specific to the requested task",
    )
    hint: Optional[str] = Field(
        default=None,
        description="Optional progressive disclosure guidance or warning",
        json_schema_extra={"example": "Tile 2x3 was verified using multimodal Gemini fallback."},
    )
    error: Optional[str] = Field(
        default=None,
        description="Error details if status is 'error'",
        json_schema_extra={"example": "Image file not found"},
    )
