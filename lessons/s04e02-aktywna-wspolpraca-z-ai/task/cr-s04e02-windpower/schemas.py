from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class HealthResponse(BaseModel):
    status: str = Field(
        default="healthy",
        description="Health status of the microservice",
        examples=["healthy"],
    )
    service: str = Field(
        default="cr-s04e02-windpower",
        description="Name of the Cloud Run microservice",
        examples=["cr-s04e02-windpower"],
    )
    timestamp: str = Field(
        description="Current server timestamp in ISO format",
        examples=["2026-09-20T22:00:00+02:00"],
    )


class RunTaskRequest(BaseModel):
    backend: Literal["langchain", "adk"] = Field(
        default="langchain",
        description="Agent backend selection: 'langchain' or 'adk'",
        examples=["langchain", "adk"],
    )
    session_id: str | None = Field(
        default=None,
        description="Optional custom session identifier for audit and tracing tracking",
        examples=["session_windpower_20260920_220000"],
    )
    max_iterations: int = Field(
        default=30,
        ge=1,
        le=100,
        description="Maximum agent iterations/recursion limit (default: 30)",
        examples=[30],
    )
    recursion_limit: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Direct alias for max_iterations/recursion limit",
        examples=[30],
    )
    recursion: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Direct short alias for max_iterations/recursion limit",
        examples=[30],
    )

    @model_validator(mode="after")
    def resolve_recursion_alias(self) -> "RunTaskRequest":
        if self.recursion is not None:
            self.max_iterations = self.recursion
        elif self.recursion_limit is not None:
            self.max_iterations = self.recursion_limit
        return self


class RunTaskResponse(BaseModel):
    status: str = Field(
        description="Execution status of the task ('success' or 'error')",
        examples=["success", "error"],
    )
    backend: str = Field(
        description="The agent backend used for execution",
        examples=["langchain", "adk"],
    )
    session_id: str = Field(
        description="The unique session ID associated with this execution run",
        examples=["s04e02_langchain_20260920_220000"],
    )
    flag: str = Field(
        description="Extracted course verification flag, or '[REDACTED_FLAG]' in audit reports",
        examples=["{FLG:...}", "[REDACTED_FLAG]"],
    )
    actions_taken: list[str] = Field(
        default_factory=list,
        description="List of actions executed during the run",
        examples=[["help", "get_documentation", "solve_and_execute_windpower"]],
    )
    reasoning: str = Field(
        description="Auditable chain-of-thought and verification summary of the agent's operations",
        examples=[
            "Explored Centrala API starting with help, discovered turbine documentation, recorded feathering specs, and triggered the deterministic solver to configure and verify the schedule within the 40-second window."
        ],
    )
    execution_time_seconds: float = Field(
        default=0.0,
        description="Total elapsed execution time in seconds",
        examples=[8.42],
    )
    scheduled_points_count: int = Field(
        default=0,
        description="Number of configured turbine schedule points transmitted to Centrala",
        examples=[5],
    )

    @field_validator("reasoning", mode="before")
    @classmethod
    def coerce_reasoning_to_str(cls, v: Any) -> str:
        if isinstance(v, list):
            return "\n".join(
                item.get("text", str(item)) if isinstance(item, dict) else str(item)
                for item in v
            )
        return str(v)


class ProbeWindpowerApiInput(BaseModel):
    action: str = Field(
        description="Action name to probe on the windpower API (e.g. 'help', 'get', etc.)",
        examples=["help", "get"],
    )
    params: dict[str, Any] | None = Field(
        default=None,
        description="Optional payload parameters required by the specific action (e.g. {'param': 'documentation'}, {'param': 'weather'}, {'param': 'powerplantcheck'})",
        examples=[{"param": "documentation"}, {"param": "weather"}],
    )
    auto_drain: bool = Field(
        default=True,
        description="When action='get', automatically drain and return the asynchronous report via getResult",
        examples=[True],
    )
    reasoning: str = Field(
        description="Mandatory justification explaining why this action is being probed during Phase 1",
        examples=[
            "Probing the help action to discover available API functions and parameter schemas."
        ],
    )


class ProbeWindpowerApiResponse(BaseModel):
    status: str = Field(
        description="Status of the API call ('success' or 'error')",
        examples=["success", "error"],
    )
    action: str = Field(
        description="Action that was executed",
        examples=["help"],
    )
    code: int | None = Field(
        default=None,
        description="API response code returned by Centrala",
        examples=[0, 13],
    )
    message: str = Field(
        description="Message or content returned by Centrala API",
        examples=["Windpower API help"],
    )
    data: Any | None = Field(
        default=None,
        description="Structured JSON payload returned by Centrala or drained asynchronous report",
        examples=[{"actions": {"start": {}, "get": {}}}],
    )
    hint: str | None = Field(
        default=None,
        description="Contextual hint guiding the agent's next action",
        examples=[
            "Documentation retrieved. Inspect blade angles and limits before launching the solver."
        ],
    )


class SaveDiscoveryNotesInput(BaseModel):
    file_path: str = Field(
        default="discovery_notes.md",
        description="Relative file path in the session workspace to save discovered notes",
        examples=["discovery_notes.md", "turbine_specs.json"],
    )
    notes_content: str = Field(
        description="Markdown or JSON content detailing discovered API endpoints, turbine limits, and rules",
        examples=[
            "# Turbine Specs\n- Durability threshold: 15.0 m/s\n- Feathering angle: 90\n- Production angle: 45"
        ],
    )
    reasoning: str = Field(
        description="Mandatory justification explaining the relevance of the notes being saved",
        examples=[
            "Persisting technical specifications for aerodynamic calculation and audit trail."
        ],
    )


class SaveDiscoveryNotesResponse(BaseModel):
    status: str = Field(
        description="Persistence status ('success' or 'error')",
        examples=["success"],
    )
    file_path: str = Field(
        description="Resolved path of the saved file in workspace",
        examples=["discovery_notes.md"],
    )
    message: str = Field(
        description="Status message",
        examples=["Discovery notes saved to workspace."],
    )
    hint: str | None = Field(
        default=None,
        description="Contextual guidance for next steps",
        examples=[
            "Specifications stored. You may now invoke solve_and_execute_windpower."
        ],
    )


class TurbineConfigPoint(BaseModel):
    startDate: str = Field(
        description="Date in YYYY-MM-DD format from the weather forecast",
        examples=["2026-03-24"],
    )
    startHour: str = Field(
        description="Hour in HH:00:00 format with minutes and seconds strictly set to zero",
        examples=["18:00:00"],
    )
    windMs: float = Field(
        description="Forecasted wind speed in meters per second for this hour",
        examples=[19.5],
    )
    pitchAngle: int = Field(
        description="Rotor blade pitch angle: 90 for storm feathering (protection), 0 or 45 for power production",
        examples=[90],
    )
    turbineMode: Literal["idle", "production"] = Field(
        description="Turbine operational mode: 'idle' for storm feathering / protection, 'production' for electricity generation",
        examples=["idle", "production"],
    )

    @field_validator("startHour")
    @classmethod
    def validate_start_hour(cls, v: str) -> str:
        # Enforce HH:00:00 format as strictly mandated by Centrala
        if ":" in v:
            parts = v.split(":")
            return f"{parts[0].zfill(2)}:00:00"
        return f"{v.zfill(2)}:00:00"


class ExecuteTurbineScheduleInput(BaseModel):
    reasoning: str = Field(
        description="Comprehensive justification detailing the schedule execution and turbine protection plan",
        examples=[
            "Weather forecast indicates gale winds (>14 m/s) requiring 90 degree feathering in idle mode. Earliest safe production window satisfying power plant deficit has 0 degree pitch."
        ],
    )
    configs: list[TurbineConfigPoint] | None = Field(
        default=None,
        description="Optional list of custom hourly configuration points. If omitted or partial, deterministic storm protection (>14 m/s to 90 idle) and optimal power production (0 production) are automatically synthesized.",
    )


class ExecuteTurbineScheduleResponse(BaseModel):
    status: str = Field(
        description="Status of schedule execution ('success' or 'error')",
        examples=["success"],
    )
    code: int = Field(
        description="Centrala completion code",
        examples=[0],
    )
    message: str = Field(
        description="Centrala response message or flag output",
        examples=["{FLG:...}"],
    )
    flag: str = Field(
        description="Extracted verification flag, or '[REDACTED_FLAG]'",
        examples=["{FLG:...}", "[REDACTED_FLAG]"],
    )
    scheduled_points: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of configured timestamp schedule points transmitted to Centrala",
        examples=[
            [
                {
                    "timestamp": "2026-03-24 18:00:00",
                    "pitchAngle": 90,
                    "turbineMode": "idle",
                    "unlockCode": "sig1",
                }
            ]
        ],
    )
    execution_time_seconds: float = Field(
        description="Total execution time of Phase 2 in seconds (< 40s battery limit)",
        examples=[4.85],
    )
    hint: str | None = Field(
        default=(
            "Phase 2 execution is finished. Centrala has received and validated the schedule. Do NOT call any more tools. Immediately formulate your final response following the AgentResponse format."
        ),
        description="Mandatory directive instructing the agent to stop and return final answer",
        examples=[
            "Execution complete. Do not call any further tools. Formulate your final response immediately."
        ],
    )


class SolveAndExecuteInput(BaseModel):
    reasoning: str = Field(
        description="Mandatory justification explaining why the agent is launching the time-critical Phase 2 solver",
        examples=[
            "API documentation and aerodynamic thresholds have been verified. Starting the 40s service window to solve and submit schedule."
        ],
    )
    max_safe_wind_speed: float | None = Field(
        default=None,
        description="Optional override for maximum safe wind speed threshold in m/s (if discovered from documentation)",
        examples=[15.0],
    )
    feathering_pitch_angle: int | None = Field(
        default=None,
        description="Optional override for feathering pitch angle during storm hours (default 90)",
        examples=[90],
    )
    production_pitch_angle: int | None = Field(
        default=None,
        description="Optional override for production pitch angle during power generation window (default 45)",
        examples=[45],
    )


class SolveAndExecuteResponse(BaseModel):
    status: str = Field(
        description="Status of the solver execution ('success' or 'error')",
        examples=["success"],
    )
    code: int = Field(
        description="Centrala completion code",
        examples=[0],
    )
    message: str = Field(
        description="Centrala response message or error",
        examples=["{FLG:...}"],
    )
    flag: str = Field(
        description="Extracted verification flag, or '[REDACTED_FLAG]'",
        examples=["{FLG:...}", "[REDACTED_FLAG]"],
    )
    scheduled_points: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of configured timestamp schedule points transmitted to Centrala",
        examples=[
            [
                {
                    "timestamp": "2026-03-24 18:00:00",
                    "pitchAngle": 90,
                    "turbineMode": "idle",
                    "unlockCode": "sig1",
                }
            ]
        ],
    )
    execution_time_seconds: float = Field(
        description="Total execution time of Phase 2 in seconds (must be < 40s)",
        examples=[6.45],
    )
    hint: str | None = Field(
        default=(
            "Phase 2 execution is finished. Centrala has received the schedule. Do NOT call any more tools (probe_*, save_*, solve_*). Immediately formulate your final response."
        ),
        description="Mandatory directive instructing the agent to terminate and return final answer",
        examples=[
            "Phase 2 execution complete. Do not call any further tools. Formulate your final response immediately."
        ],
    )


class AgentResponse(BaseModel):
    reasoning: str = Field(
        description="Summary of the agent's reasoning process across Phase 1 and Phase 2",
        examples=[
            "Discovered API capabilities, retrieved turbine specs, analyzed live weather, and executed optimal schedule within 40s window."
        ],
    )
    answer: str = Field(
        description="Final answer containing execution summary and the retrieved course flag",
        examples=["Schedule submitted successfully. Verification flag: {FLG:...}"],
    )
