from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator


class Coordinate(BaseModel):
    x: int = Field(
        ...,
        ge=0,
        le=9,
        description="Grid column index (0-indexed, 0=left, 9=right)",
        examples=[0, 5, 9],
    )
    y: int = Field(
        ...,
        ge=0,
        le=9,
        description="Grid row index (0-indexed, 0=top, 9=bottom)",
        examples=[0, 3, 9],
    )


class VehicleSpec(BaseModel):
    name: str = Field(
        ...,
        description="Canonical identifier of the vehicle or travel mode (e.g. 'rover', 'car', 'bike', 'foot')",
        examples=["rover", "car", "foot"],
    )
    fuel_per_move: float = Field(
        default=0.0,
        ge=0.0,
        description="Units of fuel consumed per single step/move",
        examples=[1.0, 0.5, 0.0],
    )
    food_per_move: float = Field(
        default=0.0,
        ge=0.0,
        description="Units of food portions consumed per single step/move",
        examples=[0.5, 1.0, 2.0],
    )
    speed: float = Field(
        default=1.0,
        gt=0.0,
        description="Relative speed or travel time modifier",
        examples=[1.0, 2.0],
    )
    traversable_tiles: list[str] = Field(
        default_factory=lambda: ["plain", "road", "grass", "sand", "base", "city"],
        description="List of terrain tile codes/types this vehicle is physically capable of traversing",
        examples=[["plain", "road", "base", "city"]],
    )
    description: Optional[str] = Field(
        default=None,
        description="Descriptive notes about the vehicle's capabilities or limitations",
    )


class TerrainMap(BaseModel):
    width: int = Field(default=10, description="Grid width (columns)")
    height: int = Field(default=10, description="Grid height (rows)")
    grid: list[list[str]] = Field(
        ...,
        description="10x10 matrix representing terrain tile types (e.g. 'plain', 'river', 'rock', 'tree', 'base', 'city')",
    )
    start: Coordinate = Field(
        ...,
        description="Coordinates of the starting location (Resistance Base)",
        examples=[{"x": 0, "y": 0}],
    )
    destination: Coordinate = Field(
        ...,
        description="Coordinates of the target destination (Skolwin enclave)",
        examples=[{"x": 9, "y": 9}],
    )


class DiscoveredTool(BaseModel):
    name: str = Field(..., description="Name or identifier of the tool", examples=["map_tool", "vehicle_tool"])
    url: str = Field(..., description="Target HTTP POST endpoint URL for the tool")
    description: str = Field(..., description="Description of the tool purpose, parameters, and return format")


# --- Tool Input & Response Schemas ---

class SearchToolsInput(BaseModel):
    reasoning: str = Field(
        ...,
        description="Justification explaining why this tool search query is needed and what capability is sought",
        examples=["Search for map and terrain reconnaissance tools to inspect the 10x10 grid."],
    )
    query: str = Field(
        ...,
        description="Natural language or keyword search query in English for toolsearch",
        examples=["map terrain obstacles", "vehicles speed fuel consumption"],
    )


class SearchToolsResponse(BaseModel):
    tools: list[DiscoveredTool] = Field(default_factory=list, description="List of discovered tools matching the query")
    hint: Optional[str] = Field(
        default="Inspect discovered tools and query them via invoke_remote_tool using English.",
        description="Progressive guidance hint for the agent",
    )


class InvokeRemoteToolInput(BaseModel):
    reasoning: str = Field(
        ...,
        description="Justification explaining why this specific tool and query are chosen",
        examples=["Query the vehicle specifications tool to learn fuel and food burn rates."],
    )
    tool_name: str = Field(
        ...,
        description="Canonical name of the remote tool to invoke (e.g. 'maps', 'wehicles')",
        examples=["maps", "wehicles"],
    )
    query: str = Field(
        ...,
        description="Query string sent in 'query' parameter strictly in English",
        examples=["Skolwin", "car"],
    )
    endpoint_url: Optional[str] = Field(
        default=None,
        description="Optional endpoint path or URL; automatically resolved by backend from tool_name if omitted",
    )


class RemoteToolResponse(BaseModel):
    tool_name: str = Field(..., description="Name of the invoked tool")
    records: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Top-3 results or dictionary data returned by the tool",
    )
    raw_response: Optional[str] = Field(
        default=None,
        description="Raw text or string representation of the tool output",
    )
    workspace_file: Optional[str] = Field(
        default=None,
        description="Relative path in cr-mcp-workspace where the response is persisted",
    )
    hint: Optional[str] = Field(
        default=None,
        description="Next step progressive disclosure hint",
    )


class PlanRouteInput(BaseModel):
    reasoning: str = Field(
        ...,
        description="Justification confirming all terrain obstacles and vehicle specs are resolved before solving",
        examples=["Terrain map and vehicle parameters are resolved from remote tools. Computing optimal route via deterministic solver."],
    )
    selected_vehicle: Optional[str] = Field(
        default=None,
        description="Optional pre-selected vehicle. If None, solver computes the global optimum across all vehicles and foot travel.",
        examples=["rover", "car", "foot"],
    )
    vehicle_specs: Optional[list[VehicleSpec]] = Field(
        default=None,
        description="List of vehicle specifications extracted by the agent from remote tool responses (e.g. fuel_per_move, food_per_move, speed). Directly feeds the deterministic solver.",
    )
    terrain_grid: Optional[list[list[str]]] = Field(
        default=None,
        description="Optional 10x10 matrix of terrain tiles extracted by the agent from the map tool response.",
    )


class PlanRouteResponse(BaseModel):
    vehicle: str = Field(..., description="Chosen starting vehicle or 'foot'")
    itinerary: list[str] = Field(
        ...,
        description="Full answer list starting with vehicle name and followed by movement directions",
        examples=[["rover", "right", "right", "up", "down"]],
    )
    fuel_remaining: float = Field(..., description="Remaining fuel units upon reaching destination")
    food_remaining: float = Field(..., description="Remaining food portions upon reaching destination")
    steps_count: int = Field(..., description="Total number of directional steps taken")
    verification_status: str = Field(..., description="Status from Centrala verification ('success' or 'failed')")
    flag: Optional[str] = Field(default=None, description="Course flag if successfully retrieved")
    hint: Optional[str] = Field(default=None, description="Diagnostic feedback if verification failed")


# --- API Service Schemas ---

class RunTaskRequest(BaseModel):
    backend: str = Field(
        default="langchain",
        description="Agent backend to execute: 'langchain' or 'adk'",
        examples=["langchain", "adk"],
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session ID for workspace grouping and audit logging",
    )
    force_refresh: bool = Field(
        default=False,
        description="Whether to bypass in-memory caches and re-query external tools",
    )
    recursion_limit: int = Field(
        default=30,
        ge=1,
        le=100,
        description="Maximum recursion/turn limit for agent execution graph (default: 30)",
        examples=[30, 50],
    )
    recursion: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Direct alias for recursion_limit",
        examples=[30, 50],
    )

    @model_validator(mode="after")
    def resolve_recursion_alias(self) -> "RunTaskRequest":
        if self.recursion is not None:
            self.recursion_limit = self.recursion
        return self


class RunTaskResponse(BaseModel):
    status: str = Field(..., description="Overall execution status ('success' or 'error')")
    backend: str = Field(..., description="Backend framework used ('langchain' or 'adk')")
    session_id: str = Field(..., description="Session ID used for audit logging and workspace persistence")
    flag: Optional[str] = Field(default=None, description="Redacted course flag retrieved upon mission success")
    itinerary: list[str] = Field(
        default_factory=list,
        description="Route moves sent to verification",
    )
    steps_count: int = Field(default=0, description="Total steps in route")
    fuel_remaining: float = Field(default=0.0, description="Remaining fuel")
    food_remaining: float = Field(default=0.0, description="Remaining food")
    details: Optional[str] = Field(default=None, description="Execution summary or error message")


class HealthResponse(BaseModel):
    status: str = Field(default="healthy", description="Service readiness status")
    service: str = Field(default="cr-s03e05-savethem", description="Canonical service name")
    timestamp: str = Field(..., description="Current server ISO timestamp")
