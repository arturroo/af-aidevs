from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ==========================================
# 1. CORE DOMAIN SCHEMAS
# ==========================================

class DamCoordinates(BaseModel):
    """Extracted grid dimensions and 1-indexed dam sector coordinates."""
    total_columns: int = Field(
        ...,
        ge=1,
        description="Total number of vertical columns counted on the map grid",
        json_schema_extra={"example": 10},
    )
    total_rows: int = Field(
        ...,
        ge=1,
        description="Total number of horizontal rows counted on the map grid",
        json_schema_extra={"example": 10},
    )
    dam_column: int = Field(
        ...,
        ge=1,
        description="1-indexed column coordinate of the sector containing the dam",
        json_schema_extra={"example": 3},
    )
    dam_row: int = Field(
        ...,
        ge=1,
        description="1-indexed row coordinate of the sector containing the dam",
        json_schema_extra={"example": 7},
    )
    visual_evidence: str = Field(
        ...,
        description="Description of visual cues confirming the dam location (e.g. intensified water color or weir structure)",
        json_schema_extra={"example": "Lake water shows darker blue saturation at row 7, column 3 indicating deep reservoir weir."},
    )
    reasoning: str = Field(
        ...,
        description="Step-by-step reasoning explaining grid counting and coordinate calculation",
        json_schema_extra={"example": "Grid counts 10 columns from left to right, 10 rows top to bottom. Dam sector is at column 3, row 7."},
    )


class DroneInstructionsSubmission(BaseModel):
    """Payload submitted to Centrala's verification endpoint."""
    instructions: List[str] = Field(
        ...,
        min_length=1,
        description="Ordered sequence of string commands directing the drone mission and strike",
        json_schema_extra={"example": ["start", "setTarget PWR6132PL", "flyTo 3,7", "detonate"]},
    )
    reasoning: str = Field(
        ...,
        description="Operational rationale explaining command ordering, arguments, and reset strategy",
        json_schema_extra={"example": "Initialize drone, register official target PWR6132PL, route physical flight to dam sector, detonate payload."},
    )


class DroneVerificationResponse(BaseModel):
    """Response returned by Centrala /verify endpoint."""
    code: int = Field(
        ...,
        description="HTTP status code or response status integer",
        json_schema_extra={"example": 0},
    )
    message: str = Field(
        ...,
        description="Status message, diagnostic error feedback, or flag confirmation",
        json_schema_extra={"example": "OK {FLG:STRIKE_CONFIRMED}"},
    )
    flag: Optional[str] = Field(
        default=None,
        description="Course flag token {FLG:...} if validation succeeded",
        json_schema_extra={"example": "{FLG:SAMPLE_FLAG}"},
    )
    is_success: bool = Field(
        default=False,
        description="True if flag was captured, False if error returned",
        json_schema_extra={"example": True},
    )
    hint: Optional[str] = Field(
        default=None,
        description="Suggested adjustment based on API feedback",
        json_schema_extra={"example": "Consider issuing hardReset before changing coordinate mode."},
    )


class DroneMissionResult(BaseModel):
    """Final operational outcome of the drone mission."""
    status: str = Field(
        ...,
        description="Operational state: 'success', 'failed', 'max_retries_exceeded'",
        json_schema_extra={"example": "success"},
    )
    iterations_used: int = Field(
        ...,
        ge=1,
        le=10,
        description="Total verification attempts executed",
        json_schema_extra={"example": 2},
    )
    dam_coordinates: DamCoordinates = Field(
        ...,
        description="Determined dam coordinates and visual evidence",
    )
    final_instructions: List[str] = Field(
        ...,
        description="Final sequence of instructions accepted by hub",
        json_schema_extra={"example": ["start", "setTarget PWR6132PL", "flyTo 3,7", "detonate"]},
    )
    flag: str = Field(
        ...,
        description="Captured course completion flag or [REDACTED_FLAG]",
        json_schema_extra={"example": "{FLG:REDACTED}"},
    )
    reasoning: str = Field(
        ...,
        description="Summary of mission progression and self-correction steps",
        json_schema_extra={"example": "Ingested terrain map, located dam at (3, 7), formulated instructions, adapted after 1 syntax correction."},
    )


# ==========================================
# 2. TOOL INPUT SCHEMAS (Contract-First)
# ==========================================

class DownloadMissionAssetsRequest(BaseModel):
    reasoning: str = Field(
        ...,
        description="Justification explaining why downloading map and documentation is required",
        json_schema_extra={"example": "Download drone map image and API documentation into workspace for analysis."},
    )


class InspectDamCoordinatesRequest(BaseModel):
    reasoning: str = Field(
        ...,
        description="Justification explaining why vision inspection of dam sector is required",
        json_schema_extra={"example": "Invoke Vision Worker to locate dam coordinates on drone.png using Gemini 3.8 Flash."},
    )


class ListMarkdownSectionsRequest(BaseModel):
    reasoning: str = Field(
        ...,
        description="Justification explaining why markdown section listing is needed",
        json_schema_extra={"example": "Scan documentation headers to locate flight control, target specification, and reset commands."},
    )
    file_path: str = Field(
        default="drone.md",
        description="Relative path of the markdown manual in workspace",
        json_schema_extra={"example": "drone.md"},
    )


class ReadMarkdownSectionRequest(BaseModel):
    section_heading: str = Field(
        ...,
        description="Exact heading or title of the markdown section to read",
        json_schema_extra={"example": "Flight Controls"},
    )
    reasoning: str = Field(
        ...,
        description="Justification explaining why reading this specific documentation section is needed",
        json_schema_extra={"example": "Inspect flight controls syntax and decoy command warnings."},
    )
    file_path: str = Field(
        default="drone.md",
        description="Relative path of the markdown manual in workspace",
        json_schema_extra={"example": "drone.md"},
    )


class ReadFileLinesRequest(BaseModel):
    start_line: int = Field(
        ...,
        ge=1,
        description="1-indexed line number from which to start reading",
        json_schema_extra={"example": 1},
    )
    line_count: int = Field(
        ...,
        ge=1,
        le=100,
        description="Maximum number of lines to read",
        json_schema_extra={"example": 30},
    )
    reasoning: str = Field(
        ...,
        description="Justification explaining why reading these specific lines is needed",
        json_schema_extra={"example": "Examine concrete command syntax examples around line 45."},
    )
    file_path: str = Field(
        default="drone.md",
        description="Relative path of the file to inspect in workspace",
        json_schema_extra={"example": "drone.md"},
    )


class GrepDocumentationRequest(BaseModel):
    pattern: str = Field(
        ...,
        description="Search pattern or keyword to grep within documentation",
        json_schema_extra={"example": "hardReset"},
    )
    reasoning: str = Field(
        ...,
        description="Justification explaining why this keyword search is required",
        json_schema_extra={"example": "Search for reset command and syntax variations."},
    )
    file_path: str = Field(
        default="drone.md",
        description="Relative path of the file to search in workspace",
        json_schema_extra={"example": "drone.md"},
    )


class VerifyInstructionsRequest(BaseModel):
    instructions: List[str] = Field(
        ...,
        min_length=1,
        description="List of drone command strings to submit to Centrala /verify",
        json_schema_extra={"example": ["start", "setTarget PWR6132PL", "flyTo 3,7", "detonate"]},
    )
    reasoning: str = Field(
        ...,
        description="Operational justification for submitting this instruction sequence",
        json_schema_extra={"example": "Submitting flight plan with official target PWR6132PL and strike target at dam coordinates."},
    )


# ==========================================
# 3. HTTP RUN ENDPOINT SCHEMAS
# ==========================================

class HealthResponse(BaseModel):
    status: str = Field(..., description="Service status", json_schema_extra={"example": "ok"})
    service: str = Field(..., description="Service name", json_schema_extra={"example": "cr-s02e05-drone"})
    version: str = Field(..., description="Service version", json_schema_extra={"example": "0.1.0"})


class RunTaskRequest(BaseModel):
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session identifier. If not provided, a standardized Zurich timestamp ID will be generated.",
        json_schema_extra={"example": "s02e05_langchain_20260910_120000"},
    )
    backend: Optional[str] = Field(
        default="langchain",
        description="Agent backend to execute ('langchain' or 'adk')",
        json_schema_extra={"example": "langchain"},
    )
    max_iterations: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Maximum verification retries",
        json_schema_extra={"example": 10},
    )


class RunTaskResponse(BaseModel):
    status: str = Field(
        ...,
        description="Status of execution ('success' or 'error')",
        json_schema_extra={"example": "success"},
    )
    session_id: str = Field(
        ...,
        description="Authoritative session identifier",
        json_schema_extra={"example": "s02e05_langchain_20260910_120000"},
    )
    backend: str = Field(
        ...,
        description="Backend framework used ('langchain' or 'adk')",
        json_schema_extra={"example": "langchain"},
    )
    flag: Optional[str] = Field(
        default=None,
        description="Captured course flag {FLG:...}",
        json_schema_extra={"example": "{FLG:SAMPLE_FLAG}"},
    )
    iterations: int = Field(
        ...,
        description="Number of verification attempts made",
        json_schema_extra={"example": 2},
    )
    dam_coordinates: Optional[DamCoordinates] = Field(
        default=None,
        description="Dam coordinates discovered during visual phase",
    )
    instructions: List[str] = Field(
        default_factory=list,
        description="Accepted drone instruction sequence",
    )
    summary: str = Field(
        ...,
        description="Execution summary message or error details",
        json_schema_extra={"example": "Mission completed successfully. Flag captured."},
    )
