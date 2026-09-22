"""Unit tests for contract-first schemas in S04E03 cr-s04e03-domatowo."""

from schemas import (
    AgentResponse,
    AlternativeDropoffRoute,
    CalculateRouteInput,
    CalculateRouteResponse,
    DomatowoApiInput,
    DomatowoApiResponse,
    MissionStateCheckpoint,
    RouteLeg,
    RunTaskRequest,
    RunTaskResponse,
    TerrainType,
    WorkspaceFileReadInput,
    WorkspaceFileReadResponse,
    WorkspaceFileWriteInput,
    WorkspaceFileWriteResponse,
)


def test_terrain_type_ontology():
    assert TerrainType.ULICA == "UL"
    assert TerrainType.BLOK_3P == "B3"
    assert TerrainType.DRZEWA == "DR"
    assert TerrainType.PUSTA_PRZESTRZEN == " "


def test_run_task_request_defaults():
    req = RunTaskRequest()
    assert req.backend == "langchain"
    assert req.session_id is None

    req_adk = RunTaskRequest(backend="adk", session_id="test-session")
    assert req_adk.backend == "adk"
    assert req_adk.session_id == "test-session"


def test_run_task_response():
    resp = RunTaskResponse(
        success=True,
        flag="{FLG:DOMATOWO_SAVED}",
        backend_used="langchain",
        ap_spent=48,
        final_location="F2",
    )
    assert resp.success is True
    assert resp.flag == "{FLG:DOMATOWO_SAVED}"
    assert resp.ap_spent == 48
    assert resp.final_location == "F2"


def test_domatowo_api_schemas():
    inp = DomatowoApiInput(
        action="help",
        params={},
        reasoning="Discovering API capabilities",
    )
    assert inp.action == "help"

    out = DomatowoApiResponse(
        status="success",
        response={"code": 0, "message": "OK"},
        ap_spent_estimate=15,
        ap_remaining_estimate=285,
        hint="Next step: query getMap",
    )
    assert out.status == "success"
    assert out.ap_spent_estimate == 15
    assert out.ap_remaining_estimate == 285


def test_calculate_route_schemas():
    inp = CalculateRouteInput(
        origin="B1",
        destination="F2",
        unit_type="transporter",
        reasoning="Navigating to candidate high-rise block",
    )
    assert inp.origin == "B1"
    assert inp.unit_type == "transporter"

    # Direct route response
    direct_resp = CalculateRouteResponse(
        direct_route_possible=True,
        route=RouteLeg(
            path=["B1", "C1", "D1"],
            steps=2,
            ap_cost=2,
            unit_type="transporter",
        ),
        tactical_briefing="Direct route available (2 steps, 2 AP).",
    )
    assert direct_resp.direct_route_possible is True
    assert direct_resp.route is not None
    assert direct_resp.route.ap_cost == 2

    # Alternative drop-off route response
    alt_resp = CalculateRouteResponse(
        direct_route_possible=False,
        reason="F2 is off-road",
        recommended_alternative_route=AlternativeDropoffRoute(
            dropoff_tile="E2",
            transporter_path=["B1", "C1", "D1", "D2", "E2"],
            transporter_ap_cost=4,
            scout_foot_path=["E2", "F2"],
            scout_ap_cost=7,
            total_trip_ap_cost=11,
        ),
        tactical_briefing="Drive transporter to E2 (4 AP), disembark scout, walk 1 step to F2 (7 AP). Total: 11 AP.",
    )
    assert alt_resp.direct_route_possible is False
    assert alt_resp.recommended_alternative_route is not None
    assert alt_resp.recommended_alternative_route.total_trip_ap_cost == 11


def test_workspace_file_schemas():
    read_inp = WorkspaceFileReadInput(file_path="todos.md", reasoning="Check checklist")
    assert read_inp.file_path == "todos.md"

    read_out = WorkspaceFileReadResponse(
        status="success", file_path="todos.md", content="# Plan"
    )
    assert read_out.content == "# Plan"

    write_inp = WorkspaceFileWriteInput(
        file_path="todos.md", content="# Update", reasoning="Update state"
    )
    assert write_inp.content == "# Update"

    write_out = WorkspaceFileWriteResponse(
        status="success", file_path="todos.md", bytes_written=8
    )
    assert write_out.bytes_written == 8


def test_mission_state_checkpoint():
    cp = MissionStateCheckpoint(
        step=4,
        checkpoint_id="cp-04-north-cleared",
        timestamp="2026-09-21 23:27:30",
        last_action="inspect('F1') -> survivor not found",
        ap_remaining_estimate=258,
        visited_clusters=["North (F1-G2)"],
        inspected_tiles=["F2", "G2", "G1", "F1"],
        current_position="Transporter at E2, Scout at F1",
        survivor_found=False,
    )
    assert cp.step == 4
    assert cp.survivor_found is False
    assert len(cp.inspected_tiles) == 4


def test_agent_response_schema():
    res = AgentResponse(
        reasoning="Executed search mission successfully.",
        answer="Partisan found at F2 and evacuated.",
        flag="{FLG:DOMATOWO_CLEARED}",
        ap_spent=52,
        survivor_tile="F2",
    )
    assert res.flag == "{FLG:DOMATOWO_CLEARED}"
    assert res.survivor_tile == "F2"
