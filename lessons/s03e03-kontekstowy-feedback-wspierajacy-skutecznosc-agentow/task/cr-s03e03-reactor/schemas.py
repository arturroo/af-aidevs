from typing import List, Literal, Optional
from pydantic import BaseModel, Field

CommandType = Literal["start", "reset", "right", "left", "wait"]


class BlockState(BaseModel):
    """Represents a vertically oscillating 2-cell reactor core obstacle."""

    column: int = Field(
        ...,
        description="Column index (1 to 7) where the reactor block is located",
        examples=[3],
    )
    top_row: int = Field(
        ...,
        description="Top row (1 to 4) occupied by the 2-cell block",
        examples=[2],
    )
    direction: Literal["up", "down"] = Field(
        ...,
        description="Current vertical movement direction of the block",
        examples=["down"],
    )


class BoardState(BaseModel):
    """Structured telemetry of the 7x5 reactor floor chamber."""

    step: int = Field(0, description="Elapsed simulation step counter", examples=[3])
    robot_column: int = Field(
        1, description="Current robot column along Row 5", examples=[1]
    )
    robot_row: int = Field(
        5, description="Floor row occupied by robot (always 5)", examples=[5]
    )
    blocks: List[BlockState] = Field(
        default_factory=list, description="States of all active vertical blocks"
    )
    raw_map: Optional[List[str]] = Field(
        None, description="Raw ASCII representation of the 7x5 chamber"
    )
    message: str = Field(
        "", description="Status message or feedback from the reactor API"
    )


class StartMissionInput(BaseModel):
    """Input payload for initiating the reactor navigation mission."""

    reasoning: str = Field(
        ...,
        description="Explicit reasoning justification for initiating the simulation session",
        examples=["Initialize reactor telemetry and retrieve initial block positions."],
    )


class StartMissionResponse(BaseModel):
    """Telemetry response after issuing the initial start command."""

    status: str = Field(..., description="Simulation initialization status")
    board_state: BoardState = Field(..., description="Initial chamber board telemetry")
    message: str = Field(..., description="API feedback message")
    hint: Optional[str] = Field(
        "Use calculate_safe_trajectory to evaluate the optimal collision-free path.",
        description="Progressive execution hint",
    )


class CalculateTrajectoryInput(BaseModel):
    """Input parameters for the discrete kinematic State-Space BFS pathfinder."""

    reasoning: str = Field(
        ...,
        description="Explanation of why trajectory calculation or recalculation is requested",
        examples=["Calculate shortest collision-free sequence from Column 1 to Column 7."],
    )
    target_column: int = Field(
        7,
        description="Target destination column index along Row 5 (default: 7 for slot G)",
        examples=[7],
    )


class CalculateTrajectoryResponse(BaseModel):
    """Computed optimal trajectory guaranteed to avoid moving reactor blocks."""

    planned_commands: List[CommandType] = Field(
        ...,
        description="Sequence of discrete actions guaranteed to reach goal without collisions",
        examples=[["wait", "right", "right", "wait", "right", "right", "right"]],
    )
    estimated_steps: int = Field(
        ..., description="Total command steps in the planned trajectory", examples=[7]
    )
    reasoning: str = Field(
        ...,
        description="Mathematical explanation of the calculated trajectory and obstacle cycles",
    )
    hint: Optional[str] = Field(
        "Execute the planned commands sequentially using step_robot.",
        description="Progressive execution hint",
    )


class StepRobotInput(BaseModel):
    """Input payload for issuing a single discrete navigation action."""

    reasoning: str = Field(
        ...,
        description="Justification for selecting this specific command at the current step",
        examples=["Step forward to Column 2 as the column block is currently elevated."],
    )
    command: CommandType = Field(
        ...,
        description="Single discrete action: right, left, or wait",
        examples=["right"],
    )


class StepRobotResponse(BaseModel):
    """Telemetry response after executing a single robot command."""

    command_executed: CommandType = Field(..., description="Action dispatched")
    current_column: int = Field(..., description="Robot column after executing the command")
    is_goal_reached: bool = Field(..., description="True if robot reached Column 7 slot G")
    is_collision: bool = Field(..., description="True if robot suffered a collision")
    message: str = Field(..., description="API status message or collision alert")
    flag: Optional[str] = Field(
        None, description="Course completion verification flag if goal reached"
    )
    raw_map: Optional[List[str]] = Field(None, description="Updated ASCII grid preview")
    hint: Optional[str] = Field(
        None, description="Next step advice or recovery instruction"
    )


class ResetSimulationInput(BaseModel):
    """Input payload for emergency recovery reset."""

    reasoning: str = Field(
        ...,
        description="Justification for resetting the simulation session",
        examples=["Desynchronization or deadlock detected; resetting chamber state."],
    )


class ResetSimulationResponse(BaseModel):
    """Outcome of emergency simulation reset."""

    status: str = Field(..., description="Reset status")
    board_state: BoardState = Field(..., description="Resynchronized board state")
    message: str = Field(..., description="API feedback message")
    hint: Optional[str] = Field(
        "Recalculate trajectory using calculate_safe_trajectory.",
        description="Next step advice",
    )


class HealthResponse(BaseModel):
    """Canonical microservice health check payload."""

    status: str = "ok"
    service: str = "cr-s03e03-reactor"
    version: str = "0.1.0"


class RunTaskRequest(BaseModel):
    """Request payload for executing the autonomous navigation mission."""

    backend: Optional[str] = Field(
        "langchain",
        description="Agent backend: 'langchain' or 'adk'",
        examples=["langchain"],
    )
    session_id: Optional[str] = Field(
        None,
        description="Explicit session ID or None for auto-generated Europe/Zurich format",
    )
    max_iterations: Optional[int] = Field(
        25, description="Maximum agent supervisory reasoning steps", examples=[25]
    )


class RunTaskResponse(BaseModel):
    """Unified execution response payload."""

    status: str = Field(..., description="Mission outcome: success or failure")
    backend: str = Field(..., description="Agent framework backend used")
    session_id: str = Field(..., description="Session identifier")
    steps_executed: int = Field(..., description="Total command steps dispatched to API")
    planned_commands: Optional[List[str]] = Field(
        None, description="Planned command sequence"
    )
    executed_commands: Optional[List[str]] = Field(
        None, description="Actual command sequence executed"
    )
    flag: Optional[str] = Field(
        None, description="Retrieved course completion flag {FLG:...}"
    )
    details: str = Field(..., description="Human-readable outcome summary")
