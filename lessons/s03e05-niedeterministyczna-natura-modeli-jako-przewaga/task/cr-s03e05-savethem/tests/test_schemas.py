"""Unit tests for contract-first schemas."""

import pytest
from pydantic import ValidationError
from schemas import (
    Coordinate,
    DiscoveredTool,
    HealthResponse,
    InvokeRemoteToolInput,
    PlanRouteInput,
    PlanRouteResponse,
    RunTaskRequest,
    RunTaskResponse,
    SearchToolsInput,
    TerrainMap,
    VehicleSpec,
)


def test_coordinate_validations():
    c = Coordinate(x=0, y=9)
    assert c.x == 0
    assert c.y == 9

    with pytest.raises(ValidationError):
        Coordinate(x=-1, y=5)

    with pytest.raises(ValidationError):
        Coordinate(x=10, y=5)


def test_vehicle_spec():
    v = VehicleSpec(
        name="rover",
        fuel_per_move=1.0,
        food_per_move=0.5,
        speed=1.5,
        traversable_tiles=["plain", "sand"],
    )
    assert v.name == "rover"
    assert v.fuel_per_move == 1.0
    assert v.food_per_move == 0.5


def test_terrain_map():
    grid = [["plain" for _ in range(10)] for _ in range(10)]
    t = TerrainMap(
        grid=grid,
        start=Coordinate(x=0, y=0),
        destination=Coordinate(x=9, y=9),
    )
    assert t.width == 10
    assert t.height == 10
    assert len(t.grid) == 10


def test_search_tools_input_requires_reasoning():
    with pytest.raises(ValidationError):
        SearchToolsInput(query="test")

    inp = SearchToolsInput(reasoning="testing rationale", query="test query")
    assert inp.query == "test query"


def test_plan_route_response():
    resp = PlanRouteResponse(
        vehicle="rover",
        itinerary=["rover", "right", "right", "up"],
        fuel_remaining=8.0,
        food_remaining=9.0,
        steps_count=3,
        verification_status="success",
        flag="{FLG:TEST_123}",
    )
    assert resp.steps_count == 3
    assert resp.flag == "{FLG:TEST_123}"


def test_run_task_request_recursion_params():
    # Default is 30
    req_default = RunTaskRequest()
    assert req_default.recursion_limit == 30

    # Explicit recursion_limit
    req_explicit = RunTaskRequest(recursion_limit=45)
    assert req_explicit.recursion_limit == 45

    # Direct alias 'recursion'
    req_alias = RunTaskRequest(recursion=50)
    assert req_alias.recursion_limit == 50

    # Invalid range bounds
    with pytest.raises(ValidationError):
        RunTaskRequest(recursion=0)

    with pytest.raises(ValidationError):
        RunTaskRequest(recursion_limit=101)


def test_invoke_remote_tool_input_optional_endpoint():
    # Without endpoint_url
    inp = InvokeRemoteToolInput(
        reasoning="Test reasoning",
        tool_name="maps",
        query="Skolwin",
    )
    assert inp.tool_name == "maps"
    assert inp.query == "Skolwin"
    assert inp.endpoint_url is None

    # With endpoint_url
    inp_with = InvokeRemoteToolInput(
        reasoning="Test reasoning",
        tool_name="maps",
        query="Skolwin",
        endpoint_url="/api/maps",
    )
    assert inp_with.endpoint_url == "/api/maps"


