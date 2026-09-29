from unittest.mock import AsyncMock, patch

import pytest

from schemas import RunTaskRequest
from services.trajectory_orchestrator import TrajectoryOrchestrator


@pytest.mark.asyncio
async def test_run_mission_successful_flow() -> None:
    orchestrator = TrajectoryOrchestrator()

    with (
        patch(
            "services.central_api_service.central_api.configure",
            new_callable=AsyncMock,
        ) as mock_cfg,
        patch(
            "services.central_api_service.central_api.get_config",
            new_callable=AsyncMock,
        ) as mock_get_cfg,
        patch(
            "services.cockpit_client.cockpit_client.set_controls",
            new_callable=AsyncMock,
        ) as mock_set_ctrl,
        patch(
            "services.cockpit_client.cockpit_client.activate_jump",
            new_callable=AsyncMock,
        ) as mock_act_jump,
        patch(
            "services.stabilization_service.stabilization_service.resolve_stabilization",
            new_callable=AsyncMock,
        ) as mock_resolve_stab,
        patch(
            "services.audit_service.audit_service.log_event",
            new_callable=AsyncMock,
        ),
    ):
        mock_get_cfg.return_value = {"advice": "Atmospheric conditions nominal."}
        mock_resolve_stab.return_value = "0"
        mock_set_ctrl.return_value = {"flux_density": 100}

        # Sequence of 3 jump responses for Phase 1, Phase 2, Phase 3
        mock_act_jump.side_effect = [
            {
                "success": True,
                "jump_code": 13,
                "battery_status": "3/3",
                "message": "Phase 1 complete",
            },
            {
                "success": True,
                "jump_code": 13,
                "battery_status": "2/3",
                "message": "Phase 2 complete",
            },
            {
                "success": True,
                "jump_code": 13,
                "battery_status": "0/3",
                "flag": "{FLG:CHRONOS_TIMETRAVEL_VICTORY}",
                "message": "Phase 3 complete",
            },
        ]

        req = RunTaskRequest(session_id="test-run-001")
        resp = await orchestrator.run_mission(req)

        assert resp.success is True
        assert resp.session_id == "test-run-001"
        assert resp.flag == "{FLG:CHRONOS_TIMETRAVEL_VICTORY}"
        assert len(resp.phases_completed) == 3
        assert resp.phases_completed[0].target == "2238-11-05"
        assert resp.phases_completed[1].target == "2026-09-29"
        assert resp.phases_completed[2].target == "2024-11-12"
        assert mock_cfg.call_count >= 12  # year, month, day, syncRatio, stab * 3


@pytest.mark.asyncio
async def test_run_mission_dynamic_targets() -> None:
    orchestrator = TrajectoryOrchestrator()

    with (
        patch(
            "services.central_api_service.central_api.configure",
            new_callable=AsyncMock,
        ),
        patch(
            "services.central_api_service.central_api.get_config",
            new_callable=AsyncMock,
        ) as mock_get_cfg,
        patch(
            "services.cockpit_client.cockpit_client.set_controls",
            new_callable=AsyncMock,
        ) as mock_set_ctrl,
        patch(
            "services.cockpit_client.cockpit_client.activate_jump",
            new_callable=AsyncMock,
        ) as mock_act_jump,
        patch(
            "services.stabilization_service.stabilization_service.resolve_stabilization",
            new_callable=AsyncMock,
        ) as mock_resolve_stab,
        patch(
            "services.audit_service.audit_service.log_event",
            new_callable=AsyncMock,
        ),
    ):
        mock_get_cfg.return_value = {
            "config": {"currentDate": "2026-09-29"},
            "needConfig": "Nominal conditions.",
        }
        mock_resolve_stab.return_value = "0"
        mock_set_ctrl.return_value = {"flux_density": 100}

        mock_act_jump.side_effect = [
            {"success": True, "jump_code": 13, "message": "Hop 1 complete"},
            {"success": True, "jump_code": 13, "message": "Hop 2 complete"},
            {"success": True, "jump_code": 13, "message": "Hop 3 complete"},
            {
                "success": True,
                "jump_code": 13,
                "flag": "{FLG:MARTY_SECRET}",
                "message": "Hop 4 complete",
            },
        ]

        req = RunTaskRequest(
            session_id="test-marty-001",
            targets=["1885-09-02", "1955-11-05", "1985-10-26", "2015-10-21"],
            is_tunnel_last=False,
        )
        resp = await orchestrator.run_mission(req)

        assert resp.success is True
        assert resp.session_id == "test-marty-001"
        assert resp.flag == "{FLG:MARTY_SECRET}"
        assert len(resp.phases_completed) == 4
        assert resp.phases_completed[0].target == "1885-09-02"
        assert resp.phases_completed[1].target == "1955-11-05"
        assert resp.phases_completed[2].target == "1985-10-26"
        assert resp.phases_completed[3].target == "2015-10-21"
