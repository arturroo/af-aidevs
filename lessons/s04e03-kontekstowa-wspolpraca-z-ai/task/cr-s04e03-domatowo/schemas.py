from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TerrainType(StrEnum):
    """Canonical terrain symbol ontology for the Domatowo 11x11 city grid."""

    ULICA = "UL"  # Street (Transporter 1 AP, Scout 7 AP)
    DRZEWA = "DR"  # Trees (Obstacle)
    PUSTA_PRZESTRZEN = " "  # Empty / Ruins (Scout 7 AP)
    BLOK_1P = "B1"  # 1-Story Block
    BLOK_2P = "B2"  # 2-Story Block
    BLOK_3P = "B3"  # 3-Story Block (Highest Residential - Survivor Location!)
    KOSCIOL = "KS"  # Church
    SZKOLA = "SZ"  # School
    PARKING = "PK"  # Parking Lot
    BOISKO = "BS"  # Sports Pitch


# REST API Schemas
class RunTaskRequest(BaseModel):
    backend: Literal["langchain", "adk"] = Field(
        default="langchain",
        description="Agent backend framework to execute.",
        examples=["langchain", "adk"],
    )
    session_id: str | None = Field(
        default=None,
        description="Optional unique session identifier for tracing and workspace isolation.",
        examples=["session-20260921-120000"],
    )
    max_iterations: int = Field(
        default=120,
        ge=1,
        le=300,
        description="Maximum agent iterations / recursion limit.",
        examples=[120],
    )
    recursion_limit: int | None = Field(
        default=None,
        ge=1,
        le=300,
        description="Direct alias for max_iterations/recursion limit.",
        examples=[120],
    )


class RunTaskResponse(BaseModel):
    success: bool = Field(
        description="Whether the mission succeeded and flag was extracted.",
        examples=[True],
    )
    flag: str | None = Field(
        default=None,
        description="Extracted Centrala verification flag {FLG:...}.",
        examples=["{FLG:REDACTED}"],
    )
    backend_used: str = Field(
        description="Framework backend executed.",
        examples=["langchain"],
    )
    ap_spent: int = Field(
        description="Total Action Points consumed during the mission.",
        examples=[48],
    )
    final_location: str | None = Field(
        default=None,
        description="Grid tile where survivor was verified and evacuated.",
        examples=["F2"],
    )
    error: str | None = Field(
        default=None,
        description="Error diagnostic message if mission aborted.",
        examples=[None],
    )


# Agent Tool 1: Centrala Meta-Tool Schemas
class DomatowoApiInput(BaseModel):
    action: str = Field(
        description="The action/command name to execute against Centrala's Domatowo API (e.g. 'help', or any action discovered from the help manual).",
        examples=["help"],
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Action-specific parameters dictionary matching the requirements discovered in the API manual (e.g. empty dict {} if action requires no params).",
        examples=[{}, {"type": "transporter", "passengers": 2}],
    )
    reasoning: str = Field(
        description="Tactical rationale explaining why this action is being dispatched at this operational step.",
        examples=[
            "Querying help endpoint to discover API capabilities from first principles."
        ],
    )


class DomatowoApiResponse(BaseModel):
    status: Literal["success", "error"] = Field(
        description="Execution status ('success' or 'error').",
        examples=["success"],
    )
    response: dict[str, Any] = Field(
        description="Raw JSON response received from Centrala.",
        examples=[{"code": 0, "message": "OK"}],
    )
    ap_spent_estimate: int = Field(
        description="Cumulative estimated Action Points consumed so far.",
        examples=[15],
    )
    ap_remaining_estimate: int = Field(
        description="Estimated remaining Action Points from the 300 AP budget.",
        examples=[285],
    )
    hint: str | None = Field(
        default=None,
        description="Progressive tactical hint for next action.",
        examples=[
            "Review response details and proceed with the next tactical milestone."
        ],
    )


# Agent Tool 2: Tactical Navigation & Route Calculator Schemas
class CalculateRouteInput(BaseModel):
    origin: str = Field(
        description="Starting tile coordinate (e.g. 'B1', 'D6', 'E2').",
        examples=["B1"],
    )
    destination: str | None = Field(
        default=None,
        description="Target tile coordinate (e.g. 'F2', 'B10'). Either destination or target_symbol must be provided.",
        examples=["F2"],
    )
    target_symbol: str | None = Field(
        default=None,
        description="Optional terrain type symbol to find the nearest candidate (e.g. 'B3' or 'BLOK_3P').",
        examples=["BLOK_3P", "B3"],
    )
    unit_type: Literal["transporter", "scout"] = Field(
        description="Type of unit to navigate ('transporter' for road-only, 'scout' for foot terrain).",
        examples=["transporter"],
    )
    reasoning: str = Field(
        description="Tactical rationale for computing this route.",
        examples=[
            "Determining minimal AP road path to approach the candidate North residential block."
        ],
    )


class RouteLeg(BaseModel):
    path: list[str] = Field(
        description="Ordered sequence of tile coordinates forming the direct path.",
        examples=[["B1", "C1", "D1", "D2", "E2"]],
    )
    steps: int = Field(
        description="Number of movement steps in this leg.",
        examples=[4],
    )
    ap_cost: int = Field(
        description="Total AP cost for this movement.",
        examples=[4],
    )
    unit_type: str = Field(
        description="Unit type executing this leg.",
        examples=["transporter"],
    )


class AlternativeDropoffRoute(BaseModel):
    dropoff_tile: str = Field(
        description="Recommended street tile to disembark scouts adjacent to target.",
        examples=["E2"],
    )
    transporter_path: list[str] = Field(
        description="Road path sequence for the transporter to reach the drop-off tile.",
        examples=[["B1", "C1", "D1", "D2", "E2"]],
    )
    transporter_ap_cost: int = Field(
        description="AP cost of transporter drive (1 AP/tile).",
        examples=[4],
    )
    scout_foot_path: list[str] = Field(
        description="Foot path sequence for the scout from drop-off to destination tile.",
        examples=[["E2", "F2"]],
    )
    scout_ap_cost: int = Field(
        description="AP cost of scout foot march (7 AP/tile).",
        examples=[7],
    )
    total_trip_ap_cost: int = Field(
        description="Combined AP cost of vehicle drive + foot march.",
        examples=[11],
    )


class CalculateRouteResponse(BaseModel):
    direct_route_possible: bool = Field(
        description="Whether unit can directly reach destination without violating terrain rules.",
        examples=[False],
    )
    route: RouteLeg | None = Field(
        default=None,
        description="Direct route details if direct_route_possible is True.",
    )
    reason: str | None = Field(
        default=None,
        description="Diagnostic explanation if direct route is not possible.",
        examples=["Destination F2 is off-road for transporter"],
    )
    recommended_alternative_route: AlternativeDropoffRoute | None = Field(
        default=None,
        description="Optimal drop-off route if destination is off-road for transporter.",
    )
    tactical_briefing: str = Field(
        description="Concise tactical briefing of the calculated route.",
        examples=[
            "Drive transporter to drop-off tile E2 (4 AP), disembark scout, walk 1 step to F2 (7 AP). Total: 11 AP."
        ],
    )
    hint: str | None = Field(
        default=None,
        description="Tactical advice for the commanding agent.",
        examples=[
            "Execute transporter movement to drop-off tile, disembark scout, and enter building."
        ],
    )


# Agent Tool 3 & 4: Workspace File Memory Schemas
class WorkspaceFileReadInput(BaseModel):
    file_path: str = Field(
        default="todos.md",
        description="Path of file to read in session workspace.",
        examples=["todos.md"],
    )
    reasoning: str = Field(
        description="Reasoning for inspecting the workspace file.",
        examples=["Checking current mission checklist and inspected tiles state."],
    )


class WorkspaceFileReadResponse(BaseModel):
    status: Literal["success", "error", "not_found"] = Field(
        description="Read status ('success', 'error', or 'not_found').",
        examples=["success"],
    )
    file_path: str = Field(
        description="Workspace file path.",
        examples=["todos.md"],
    )
    content: str = Field(
        description="Text content of the file.",
        examples=["# Mission Checklist - Domatowo\n- [x] 1. Help"],
    )
    hint: str | None = Field(
        default=None,
        description="Tactical hint.",
        examples=["Update todos.md after completing each tactical milestone."],
    )


class WorkspaceFileWriteInput(BaseModel):
    file_path: str = Field(
        default="todos.md",
        description="Path of file to write in session workspace.",
        examples=["todos.md"],
    )
    content: str = Field(
        description="Markdown or text content to store.",
        examples=["# Mission Checklist - Domatowo\n- [x] 1. Help completed"],
    )
    reasoning: str = Field(
        description="Reasoning for updating the workspace file.",
        examples=["Recording step 3 checkpoint with inspected tile F2."],
    )


class WorkspaceFileWriteResponse(BaseModel):
    status: Literal["success", "error"] = Field(
        description="Write status ('success' or 'error').",
        examples=["success"],
    )
    file_path: str = Field(
        description="Workspace file path written.",
        examples=["todos.md"],
    )
    bytes_written: int = Field(
        description="Count of bytes saved.",
        examples=[320],
    )
    hint: str | None = Field(
        default=None,
        description="Tactical hint.",
        examples=["Proceed to the next task on your checklist."],
    )


# Monotonic State Checkpoint Model
class MissionStateCheckpoint(BaseModel):
    step: int = Field(
        description="Monotonically increasing step sequence number.",
        examples=[4],
    )
    checkpoint_id: str = Field(
        description="Semantic checkpoint slug.",
        examples=["cp-04-north-cleared"],
    )
    timestamp: str = Field(
        description="Timestamp of checkpoint (yyyy-MM-dd HH:mm:ss).",
        examples=["2026-09-21 23:27:30"],
    )
    last_action: str = Field(
        description="Summary of last executed action and result.",
        examples=["inspect('F1') -> survivor not found"],
    )
    ap_remaining_estimate: int = Field(
        description="Estimated remaining AP balance.",
        examples=[258],
    )
    visited_clusters: list[str] = Field(
        default_factory=list,
        description="List of cluster identifiers already swept.",
        examples=[["North (F1-G2)"]],
    )
    inspected_tiles: list[str] = Field(
        default_factory=list,
        description="List of exact tile coordinates already inspected.",
        examples=[["F2", "G2", "G1", "F1"]],
    )
    current_position: str = Field(
        description="Current operational position of units.",
        examples=["Transporter at E2, Scout at F1"],
    )
    survivor_found: bool = Field(
        default=False,
        description="Whether survivor presence was positively confirmed.",
        examples=[False],
    )


# Final Agent Response Schema
class AgentResponse(BaseModel):
    reasoning: str = Field(
        description="Complete operational debrief explaining how the mission was executed.",
        examples=[
            "Discovered API capabilities, navigated to North cluster, confirmed survivor at F2, executed extraction."
        ],
    )
    answer: str = Field(
        description="Final concise response answering the mission mandate.",
        examples=[
            "Partisan successfully located at F2 and evacuated by helicopter. Flag retrieved: {FLG:...}"
        ],
    )
    flag: str | None = Field(
        default=None,
        description="Extracted Centrala course flag {FLG:...}.",
        examples=["{FLG:REDACTED}"],
    )
    ap_spent: int = Field(
        default=0,
        description="Total Action Points consumed during the mission.",
        examples=[48],
    )
    survivor_tile: str | None = Field(
        default=None,
        description="Grid tile where survivor was verified.",
        examples=["F2"],
    )
