"""Unit tests for contract schemas and Pydantic validation."""

from schemas import (
    DisarmPayload,
    FlightState,
    GameColumn,
    RadarTelemetryExtraction,
    RadioNavigationExtraction,
    RunTaskRequest,
    RunTaskResponse,
    TrajectoryStep,
    VerifyCommandAnswer,
    VerifyEnvelope,
)


def test_trajectory_step_creation() -> None:
    step = TrajectoryStep(
        column=3,
        row=2,
        command="go",
        rock_row=1,
        radar_locked=True,
        disarm_hash="da39a3ee5e6b4b0d3255bfef95601890afd80709",
    )
    assert step.column == 3
    assert step.row == 2
    assert step.command == "go"
    assert step.rock_row == 1
    assert step.radar_locked is True
    assert step.disarm_hash == "da39a3ee5e6b4b0d3255bfef95601890afd80709"


def test_flight_state_defaults() -> None:
    state = FlightState(session_id="test-session-123")
    assert state.current_column == 1
    assert state.current_row == 2
    assert state.target_row == 2
    assert state.current_rock_row is None
    assert state.history == []
    assert state.radar_disarms_count == 0
    assert state.is_completed is False
    assert state.flag is None

    # Adding column 1 to columns_history should dynamically update current_rock_row
    state.columns_history[1] = GameColumn(
        column=1, your_row=2, stone_row=3, free_rows=[1, 2]
    )
    assert state.current_rock_row == 3


def test_radar_telemetry_extraction_schema() -> None:
    clear_telemetry = RadarTelemetryExtraction(
        is_clear=True,
        reasoning="Sector is clear",
    )
    assert clear_telemetry.is_clear is True
    assert clear_telemetry.frequency is None
    assert clear_telemetry.detection_code is None

    locked_telemetry = RadarTelemetryExtraction(
        is_clear=False,
        frequency=432,
        detection_code="oko_trap_99",
        reasoning="Hostile tracking detected",
    )
    assert locked_telemetry.is_clear is False
    assert locked_telemetry.frequency == 432
    assert locked_telemetry.detection_code == "oko_trap_99"


def test_radio_navigation_extraction_schema() -> None:
    extraction = RadioNavigationExtraction(
        rock_relative_direction="left",
        rock_absolute_row=1,
        safe_commands=["go", "right"],
        reasoning="Shoals to port, rock is at Row 1",
    )
    assert extraction.rock_relative_direction == "left"
    assert extraction.rock_absolute_row == 1
    assert extraction.safe_commands == ["go", "right"]


def test_disarm_payload_schema() -> None:
    disarm = DisarmPayload(
        apikey="secret-key",
        frequency=123.5,
        disarmHash="c29f4f4a38e888636b2f4f89d36e2f49557b458b",
    )
    assert disarm.apikey == "secret-key"
    assert disarm.frequency == 123.5
    assert disarm.disarmHash == "c29f4f4a38e888636b2f4f89d36e2f49557b458b"


def test_verify_envelope_schema() -> None:
    envelope = VerifyEnvelope(
        apikey="secret-key",
        answer=VerifyCommandAnswer(command="left"),
    )
    assert envelope.task == "goingthere"
    assert envelope.answer.command == "left"


def test_run_task_request_and_response() -> None:
    req = RunTaskRequest(
        model="gemini-3.5-flash-lite",
        thinking_level="medium",
        direct_egress=True,
    )
    assert req.model == "gemini-3.5-flash-lite"
    assert req.thinking_level == "medium"
    assert req.direct_egress is True

    resp = RunTaskResponse(
        session_id="test-session-123",
        status="completed",
        flag="{FLG:ROCKET_TEST}",
        target_row=1,
        total_steps=11,
        radar_disarms=2,
        trajectory=[],
        execution_time_seconds=12.34,
    )
    assert resp.status == "completed"
    assert resp.flag == "{FLG:ROCKET_TEST}"
    assert resp.radar_disarms == 2


def test_dynamic_url_derivation() -> None:
    from config import Config

    cfg = Config()
    cfg.AIDEVS_API_VERIFY = "https://hub.ag3nts.org/verify"
    cfg.AIDEVS_API_GETMESSAGE = ""
    cfg.AIDEVS_API_FREQUENCY_SCANNER = ""

    assert cfg.getmessage_url == "https://hub.ag3nts.org/api/getmessage"
    assert cfg.frequency_scanner_url == "https://hub.ag3nts.org/api/frequencyScanner"


def test_game_column_schema() -> None:
    from schemas import GameColumn

    col = GameColumn(
        column=1,
        your_row=2,
        stone_row=3,
        free_rows=[1, 2],
    )
    assert col.column == 1
    assert col.your_row == 2
    assert col.stone_row == 3
    assert col.free_rows == [1, 2]
