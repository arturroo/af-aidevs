from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from af_aidevs.schemas.common import AgentResponseEnvelope
from af_aidevs.schemas.vision import (
    TilePinout,
    GridCircuitSolverData,
    VisionInspectRequest,
    VisionCircuitResponse,
)


class RotatePayload(BaseModel):
    """Payload to submit to course verification endpoint."""

    apikey: str = Field(description="User API key")
    task: str = Field(default="electricity", description="Task identifier")
    answer: Dict[str, str] = Field(
        description="Dictionary with 'rotate': 'AxB' key-value pair",
        json_schema_extra={"example": {"rotate": "2x3"}},
    )


class RotateCommand(BaseModel):
    """Domain model representing a single tile rotation action."""

    tile_id: str = Field(
        description="Grid coordinates AxB (e.g. 1x2, 2x3)",
        json_schema_extra={"example": "2x3"},
    )
    steps_cw: int = Field(
        ge=1,
        le=3,
        description="Number of 90-degree clockwise rotations needed (1, 2, or 3)",
        json_schema_extra={"example": 1},
    )


class SolverResult(BaseModel):
    """Outcome of the puzzle solver orchestration."""

    status: str = Field(description="Status of the solution run: success or error")
    rotations_executed: int = Field(description="Total number of rotation API calls made")
    flag: Optional[str] = Field(default=None, description="Course flag retrieved upon completion")
    reasoning: str = Field(description="Audit justification of actions taken")
    run_notes_path: Optional[str] = Field(default=None, description="Path where run_notes.txt was written")


__all__ = [
    "AgentResponseEnvelope",
    "TilePinout",
    "GridCircuitSolverData",
    "VisionInspectRequest",
    "VisionCircuitResponse",
    "RotatePayload",
    "RotateCommand",
    "SolverResult",
]
