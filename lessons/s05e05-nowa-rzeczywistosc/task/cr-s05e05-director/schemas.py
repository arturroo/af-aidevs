from typing import Any, Literal

from pydantic import BaseModel, Field


class PhaseResult(BaseModel):
    """Result summary for an individual temporal trajectory phase."""

    phase: int = Field(
        description="Phase index (1 = future jump, 2 = return jump, 3 = tunnel).",
        examples=[1, 2, 3],
    )
    target: str = Field(
        description="Target destination date string (YYYY-MM-DD).",
        examples=["2238-11-05", "2026-09-29", "2024-11-12"],
    )
    status: Literal["COMPLETED", "FAILED", "SKIPPED"] = Field(
        description="Execution status of this phase.",
        examples=["COMPLETED"],
    )
    battery: str | None = Field(
        default=None,
        description="Reported battery status following the jump.",
        examples=["3/3", "2/3"],
    )
    details: str | None = Field(
        default=None,
        description="Detailed execution log or notes.",
    )


class RunTaskRequest(BaseModel):
    """Execution request payload with dynamic model and iteration overrides."""

    targets: list[str] | None = Field(
        default=None,
        description="Optional list of destination dates (YYYY-MM-DD) to visit sequentially.",
        examples=[["1885-09-02", "1955-11-05", "1985-10-26", "2015-10-21"]],
    )
    is_tunnel_last: bool = Field(
        default=False,
        description="Whether the final hop should establish a time tunnel (PTA+PTB).",
    )
    recharge_first: bool = Field(
        default=False,
        description="Whether to perform an initial jump to 2238-11-05 to recharge battery to 3/3.",
    )
    model: str | None = Field(
        default=None,
        description="Optional Gemini model override.",
        examples=["gemini-3.5-flash-lite", "gemini-3.8-flash"],
    )
    thinking_level: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="Optional reflection depth override.",
        examples=["low"],
    )
    session_id: str | None = Field(
        default=None,
        description="Optional unique identifier for tracing and audit logging.",
        examples=["mission-20260929-001"],
    )
    max_iterations: int | None = Field(
        default=None,
        description="Maximum retry or loop threshold.",
        examples=[50],
    )


class RunTaskResponse(BaseModel):
    """Comprehensive response summarizing the temporal navigation mission."""

    success: bool = Field(
        description="Whether all 3 trajectory phases completed successfully.",
        examples=[True],
    )
    session_id: str = Field(
        description="Session identifier matching the execution run.",
        examples=["mission-20260929-001"],
    )
    flag: str | None = Field(
        default=None,
        description="Captured course completion flag.",
        examples=["{FLG:...}"],
    )
    execution_time_seconds: float = Field(
        description="Total elapsed execution duration.",
        examples=[18.4],
    )
    phases_completed: list[PhaseResult] = Field(
        default_factory=list,
        description="Step-by-step breakdown of each phase result.",
    )
    message: str = Field(
        description="Human-readable mission summary narrative.",
        examples=["Time tunnel locked. Rendezvous with Rafał accomplished."],
    )


class CentralVerifyEnvelope(BaseModel):
    """Payload schema for dispatching commands to the Central verify gateway."""

    apikey: str = Field(description="User API key authentication token.")
    task: str = Field(
        default="timetravel",
        description="Task identifier for time travel operations.",
    )
    answer: dict[str, Any] = Field(
        description="Action payload containing action name and parameters."
    )


class StabilizationDecision(BaseModel):
    """Structured Pydantic model for Gemini temporal stabilization interpretation."""

    stabilization_value: str = Field(
        description="Extracted or deduced stabilization setting value required by Central (e.g. '0', '1', 'auto', 'default').",
    )
    reasoning: str = Field(
        description="Brief justification explaining how the advice was parsed from the API hint.",
    )
