"""Unit tests for DomatowoService (AP accounting, Centrala communication, and workspace)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.domatowo_service import DomatowoService


@pytest.fixture
def mock_mcp():
    mcp = MagicMock()
    mcp.post_web_resource = AsyncMock()
    mcp.read_file = AsyncMock()
    mcp.write_file = AsyncMock()
    return mcp


@pytest.fixture
def mock_audit():
    audit = MagicMock()
    audit.log_event = AsyncMock()
    return audit


@pytest.fixture
def service(mock_mcp, mock_audit):
    return DomatowoService(audit_service=mock_audit, mcp_service=mock_mcp)


@pytest.mark.asyncio
async def test_ap_ledger_create_actions(service, mock_mcp):
    session_id = "test-session-1"
    mock_mcp.post_web_resource.return_value = {
        "code": 0,
        "message": "Transporter created at B1",
    }

    # Create transporter with 2 scouts: 5 base + 2*5 = 15 AP
    resp = await service.execute_action(
        session_id=session_id,
        action="create",
        params={"type": "transporter", "passengers": 2},
        reasoning="Deploying main vehicle with scouts",
    )
    assert resp.status == "success"
    assert resp.ap_spent_estimate == 15
    assert resp.ap_remaining_estimate == 285


@pytest.mark.asyncio
async def test_ap_ledger_reset_action(service, mock_mcp):
    session_id = "test-session-reset"
    mock_mcp.post_web_resource.return_value = {
        "code": 0,
        "message": "Board reset to default state. Partisan position rolled.",
    }

    # Simulate some AP spent first
    service.ap_spent[session_id] = 120

    resp = await service.execute_action(
        session_id=session_id,
        action="reset",
        params={},
        reasoning="Resetting board for clean run",
    )
    assert resp.status == "success"
    assert resp.ap_spent_estimate == 0
    assert resp.ap_remaining_estimate == 300
    assert service.get_ap_spent(session_id) == 0


@pytest.mark.asyncio
async def test_ap_ledger_movement_and_inspection(service, mock_mcp):
    session_id = "test-session-2"
    mock_mcp.post_web_resource.return_value = {"code": 0, "message": "OK"}

    # Move transporter 4 steps: 4 AP
    await service.execute_action(
        session_id=session_id,
        action="move",
        params={"type": "transporter", "path": ["B1", "C1", "D1", "D2", "E2"]},
        reasoning="Drive to drop-off",
    )
    assert service.get_ap_spent(session_id) == 4

    # Move scout 1 step: 7 AP
    await service.execute_action(
        session_id=session_id,
        action="move",
        params={"type": "scout", "steps": 1},
        reasoning="Enter building on foot",
    )
    assert service.get_ap_spent(session_id) == 11  # 4 + 7

    # Inspect tile: 1 AP
    await service.execute_action(
        session_id=session_id,
        action="inspect",
        params={"tile": "F2"},
        reasoning="Inspecting building floor",
    )
    assert service.get_ap_spent(session_id) == 12  # 11 + 1


@pytest.mark.asyncio
async def test_flag_extraction(service, mock_mcp):
    session_id = "test-session-flag"
    mock_mcp.post_web_resource.return_value = {
        "code": 0,
        "message": "Helicopter extraction successful! Centrala flag: {FLG:SURVIVOR_RESCUED_DOMATOWO}",
    }

    resp = await service.execute_action(
        session_id=session_id,
        action="callHelicopter",
        params={"destination": "F2"},
        reasoning="Calling extraction",
    )
    assert resp.status == "success"
    assert service.extracted_flags.get(session_id) == "{FLG:SURVIVOR_RESCUED_DOMATOWO}"


@pytest.mark.asyncio
async def test_workspace_file_operations(service, mock_mcp):
    session_id = "test-session-ws"
    mock_mcp.read_file.return_value = {
        "status": "success",
        "content": "# Mission Checklist",
    }
    mock_mcp.write_file.return_value = {"status": "success", "bytes_written": 25}

    read_res = await service.read_workspace_file(
        session_id, "todos.md", "Reading state"
    )
    assert read_res.status == "success"
    assert read_res.content == "# Mission Checklist"

    write_res = await service.update_workspace_file(
        session_id, "todos.md", "# New Plan", "Updating state"
    )
    assert write_res.status == "success"
    assert write_res.bytes_written == 25


def test_parse_retry_after_seconds():
    from services.mcp_service import parse_retry_after

    assert parse_retry_after("5") == 5.0
    assert parse_retry_after("2.5") == 2.5
    assert parse_retry_after("  10  ") == 10.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("invalid") is None


def test_wait_retry_after_or_exponential():
    from unittest.mock import MagicMock

    from services.mcp_service import (
        CentralaRateLimitError,
        wait_retry_after_or_exponential,
    )

    strategy = wait_retry_after_or_exponential(min_wait=1.0, max_wait=10.0)

    # State with explicit retry_after
    retry_state_with_delay = MagicMock()
    retry_state_with_delay.outcome.failed = True
    retry_state_with_delay.outcome.exception.return_value = CentralaRateLimitError(
        "Rate limit", retry_after=7.5
    )

    delay = strategy(retry_state_with_delay)
    assert delay == 7.5

    # State without retry_after (should use exponential fallback)
    retry_state_no_delay = MagicMock()
    retry_state_no_delay.outcome.failed = True
    retry_state_no_delay.outcome.exception.return_value = CentralaRateLimitError(
        "Rate limit", retry_after=None
    )
    retry_state_no_delay.attempt_number = 1

    exp_delay = strategy(retry_state_no_delay)
    assert 1.0 <= exp_delay <= 10.0
