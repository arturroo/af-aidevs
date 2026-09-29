"""Pydantic schemas and contract definitions for cr-s05e04-goingthere."""

from typing import Literal

from pydantic import BaseModel, Field


class GameColumn(BaseModel):
    """Exact representation of Centrala's currentColumn state."""

    column: int = Field(..., description="Grid column index (1-12)")
    your_row: int = Field(..., description="Rocket vertical row (1-3)")
    stone_row: int = Field(..., description="Lethal rock formation row (1-3)")
    free_rows: list[int] = Field(
        default_factory=list,
        description="List of safe vertical channels in this column",
    )


class TrajectoryStep(BaseModel):
    """Snapshot of rocket state and telemetry at a specific column."""

    column: int = Field(..., description="Longitudinal column index (1-12)")
    row: int = Field(..., description="Vertical row coordinate (1-3)")
    command: Literal["start", "go", "left", "right"] = Field(
        ..., description="Movement thrust dispatched to advance to this column"
    )
    rock_row: int | None = Field(
        default=None, description="Observed or deduced rock row in this column"
    )
    radar_locked: bool = Field(
        default=False, description="Whether an OKO radar lock was active in this column"
    )
    disarm_hash: str | None = Field(
        default=None, description="SHA-1 disarm hash submitted if locked"
    )


class FlightState(BaseModel):
    """Accumulator state tracked across the entire mission by the FSM."""

    session_id: str = Field(..., description="Unique flight session identifier")
    current_column: int = Field(default=1, description="Current column position (1-12)")
    current_row: int = Field(default=2, description="Current row position (1-3)")
    target_row: int = Field(
        default=2, description="Grudziądz destination row at column 12"
    )
    columns_history: dict[int, GameColumn] = Field(
        default_factory=dict,
        description="Historical map of all discovered columns (1-12)",
    )

    @property
    def current_rock_row(self) -> int | None:
        """Rock row in the current column derived dynamically from columns_history."""
        col = self.columns_history.get(self.current_column)
        return col.stone_row if col else None

    history: list[TrajectoryStep] = Field(
        default_factory=list, description="Historical flight progression"
    )
    radar_disarms_count: int = Field(
        default=0, description="Total active radar traps disarmed"
    )
    is_completed: bool = Field(
        default=False, description="Whether Grudziądz has been reached"
    )
    flag: str | None = Field(
        default=None, description="Extracted course flag token upon mission success"
    )


class RadarTelemetryExtraction(BaseModel):
    """Structured extraction of OKO frequency scanner status from distorted payloads."""

    is_clear: bool = Field(
        ...,
        description="True if airspace is clear ('It's clear!'), False if targeted by OKO radar",
    )
    frequency: int | float | None = Field(
        default=None,
        description="Targeting frequency identifier extracted from payload",
    )
    detection_code: str | None = Field(
        default=None,
        description="Alphanumeric detection code required for disarming hash",
    )
    reasoning: str = Field(
        default="", description="Extraction chain-of-thought analysis"
    )


class RadioNavigationExtraction(BaseModel):
    """Structured resolution of tactical maritime radio hints into grid coordinates."""

    rock_relative_direction: Literal["left", "ahead", "right", "unknown"] = Field(
        ...,
        description="Obstacle direction relative to rocket heading: left (higher row), ahead (same row), right (lower row)",
    )
    rock_absolute_row: int = Field(
        ...,
        description="Calculated absolute row (1, 2, or 3) containing the rock in next column",
    )
    safe_commands: list[Literal["go", "left", "right"]] = Field(
        ..., description="List of safe thrust commands that avoid the rock"
    )
    reasoning: str = Field(
        default="",
        description="Naval interpretation explaining maritime phrases (port/starboard/bow/shoals)",
    )


class StartMissionExtraction(BaseModel):
    """Structured extraction of mission initialization parameters."""

    start_column: int = Field(
        default=1, description="Starting rocket column, typically 1"
    )
    start_row: int = Field(default=2, description="Starting rocket row, typically 2")
    start_rock_row: int | None = Field(
        default=None,
        description="Row of the rock in column 1 if mentioned in the start message",
    )
    target_column: int = Field(
        default=12, description="Target base column, typically 12"
    )
    target_row: int = Field(
        ...,
        description="Target destination row (strictly 1, 2, or 3) where the base / flag in Grudziadz is located",
    )
    reasoning: str = Field(
        default="",
        description="Rationale explaining how start vs destination coordinates were distinguished",
    )


class DisarmPayload(BaseModel):
    """Payload sent to $AIDEVS_API_FREQUENCY_SCANNER to neutralize radar."""

    apikey: str = Field(..., description="Course API key")
    frequency: int | float = Field(..., description="Radar targeting frequency")
    disarmHash: str = Field(..., description="SHA-1 hash of detectionCode + 'disarm'")


class VerifyCommandAnswer(BaseModel):
    """Inner answer object for Centrala verify endpoint."""

    command: Literal["start", "go", "left", "right"] = Field(
        ..., description="Movement thrust command"
    )


class VerifyEnvelope(BaseModel):
    """Request envelope sent to Centrala verification endpoint."""

    apikey: str = Field(..., description="Course API key")
    task: str = Field(default="goingthere", description="Task identifier")
    answer: VerifyCommandAnswer = Field(
        ..., description="Movement command answer envelope"
    )


class RunTaskRequest(BaseModel):
    """Execution request payload for Cloud Run POST /run endpoint."""

    session_id: str | None = Field(
        default=None,
        description="Optional session ID for tracing and workspace isolation",
        examples=["session-s05e04-abc1234"],
    )
    model: str | None = Field(
        default=None,
        description="Dynamic LLM override for evaluation and testing",
        examples=["gemini-3.5-flash-lite"],
    )
    thinking_level: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="Reasoning effort level for Gemini models",
        examples=["medium"],
    )
    direct_egress: bool = Field(
        default=False,
        description="Whether to bypass cr-mcp-web-gateway and use direct httpx egress",
    )
    crash_at_column: int | None = Field(
        default=None,
        description="Optional easter egg parameter: intentionally crash the rocket when reaching this column (e.g. 6, 4, or 2)",
        examples=[6],
    )


class RunTaskResponse(BaseModel):
    """Final response returned from Cloud Run /run endpoint."""

    session_id: str = Field(
        ...,
        description="Session identifier associated with this execution run",
        examples=["session-s05e04-abc1234"],
    )
    status: Literal["completed", "failed"] = Field(
        ...,
        description="Final status of task execution",
        examples=["completed"],
    )
    flag: str | None = Field(
        default=None,
        description="Extracted course flag token if successfully reached Grudziądz",
        examples=["{FLG:...}"],
    )
    target_row: int | None = Field(
        default=None,
        description="Target destination row in Grudziądz at column 12",
        examples=[1],
    )
    total_steps: int = Field(
        ...,
        description="Total movements executed during the flight",
        examples=[11],
    )
    radar_disarms: int = Field(
        ...,
        description="Total OKO radar traps successfully disarmed",
        examples=[3],
    )
    trajectory: list[TrajectoryStep] = Field(
        default_factory=list,
        description="Complete trajectory history recorded step-by-step",
    )
    execution_time_seconds: float = Field(
        ...,
        description="Total duration of the execution run in seconds",
        examples=[16.84],
    )
    error: str | None = Field(
        default=None,
        description="Error description if status is failed",
    )
