from typing import List, Optional
from pydantic import BaseModel, Field
from af_aidevs.schemas.common import AgentResponseEnvelope


class TilePinout(BaseModel):
    """Four-way pinout representation for electrical wiring connections on a single tile."""

    top: bool = Field(description="Wire connection present on the top edge")
    right: bool = Field(description="Wire connection present on the right edge")
    bottom: bool = Field(description="Wire connection present on the bottom edge")
    left: bool = Field(description="Wire connection present on the left edge")


class GridCircuitSolverData(BaseModel):
    """Domain model representing the 3x3 rotation matrix and confidence scores."""

    rotations: List[List[int]] = Field(
        description="3x3 matrix where rotations[row][col] is the number of 90° CW rotations (0-3) needed for tile (row+1)x(col+1)",
        json_schema_extra={"example": [[0, 1, 0], [2, 0, 3], [0, 0, 1]]},
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence score of the visual analysis (0.0 to 1.0)",
        json_schema_extra={"example": 0.98},
    )
    tile_confidence: List[List[float]] = Field(
        description="3x3 matrix of confidence scores for each individual tile (0.0 to 1.0)",
        json_schema_extra={"example": [[1.0, 1.0, 1.0], [1.0, 1.0, 0.95], [1.0, 1.0, 1.0]]},
    )


class VisionInspectRequest(BaseModel):
    """A2A Request payload sent to the Vision Specialist Agent."""

    task_type: str = Field(
        default="grid_circuit_solver",
        description="Identifier of the vision task schema",
        json_schema_extra={"example": "grid_circuit_solver"},
    )
    image_path: str = Field(
        description="Relative session workspace path of the current board image PNG",
        json_schema_extra={"example": "electricity.png"},
    )
    target_image_path: str = Field(
        description="Relative session workspace path of the reference solved circuit image PNG",
        json_schema_extra={"example": "solved_electricity.png"},
    )
    grid_size: List[int] = Field(
        default=[3, 3],
        description="Dimensions of the grid [rows, cols]",
        json_schema_extra={"example": [3, 3]},
    )
    reasoning: str = Field(
        description="Justification explaining why visual inspection is requested",
        json_schema_extra={"example": "Analyzing electrical tile connections against solved target."},
    )


# Concrete response alias:
VisionCircuitResponse = AgentResponseEnvelope[GridCircuitSolverData]
