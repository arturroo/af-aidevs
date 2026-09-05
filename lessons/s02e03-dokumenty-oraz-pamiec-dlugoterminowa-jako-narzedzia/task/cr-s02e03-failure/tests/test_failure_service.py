import pytest
from services.failure_service import FailureLogProcessor
from services.token_service import TokenService

SAMPLE_RAW_LOGS = """
[2026-02-26 05:45:00] [INFO] SYS01 Routine diagnostic before startup
[2026-02-26 06:00:10] [INFO] CTRL01 Reactor startup sequence initiated
[2026-02-26 06:04:12] [CRIT] ECCS8 runaway outlet temp. Protection interlock initiated reactor trip.
[2026-02-26 06:11:30] [WARN] PWR01 input ripple crossed warning limits.
[2026-02-26 10:15:00] [CRIT] WTANK07 coolant below critical threshold. Hard trip initiated.
[2026-02-26 14:20:10] [WARN] PUMP02 auxiliary flow reduced below baseline.
[2026-02-26 21:55:00] [CRIT] GEN01 emergency disconnect trigger. Reactor shutdown complete.
[2026-02-26 23:30:00] [INFO] SYS01 Post-shutdown cool down status OK.
"""


def test_parse_line():
    proc = FailureLogProcessor()
    line = "[2026-02-26 06:04:12] [CRIT] ECCS8 runaway outlet temp. Protection interlock initiated reactor trip."
    ev = proc.parse_line(line)

    assert ev is not None
    assert ev.date_str == "2026-02-26"
    assert ev.time_str == "06:04"
    assert ev.severity == "[CRIT]"
    assert ev.component_id == "ECCS8"
    assert "reactor trip" in ev.description


def test_filter_events():
    proc = FailureLogProcessor()
    lines = SAMPLE_RAW_LOGS.strip().splitlines()
    events = [ev for l in lines if (ev := proc.parse_line(l)) is not None]

    filtered = proc.filter_events(events)

    # 05:45 INFO should be excluded (routine INFO outside start window)
    # 23:30 INFO should be excluded (after 22:00)
    # 06:04 CRIT, 06:11 WARN, 10:15 CRIT, 14:20 WARN, 21:55 CRIT should be included
    component_ids = [e.component_id for e in filtered]
    assert "ECCS8" in component_ids
    assert "PWR01" in component_ids
    assert "WTANK07" in component_ids
    assert "PUMP02" in component_ids
    assert "GEN01" in component_ids
    assert "SYS01" not in component_ids


def test_condense_events():
    proc = FailureLogProcessor()
    lines = SAMPLE_RAW_LOGS.strip().splitlines()
    events = [ev for l in lines if (ev := proc.parse_line(l)) is not None]
    filtered = proc.filter_events(events)

    text, tokens = proc.condense_events(filtered, max_tokens=1400)
    assert tokens > 0
    assert tokens <= 1400
    assert "ECCS8" in text
    assert "GEN01" in text

    # Verify multiline structure (one event per line)
    out_lines = text.splitlines()
    for l in out_lines:
        assert l.startswith("[2026-02-26 ")


def test_extract_components_from_feedback():
    proc = FailureLogProcessor()
    feedback = "Technicy zwracają uwagę, że brakuje danych dla podzespołu PUMP02 oraz poziomu w WTANK07."
    comps = proc.extract_components_from_feedback(feedback)
    assert "PUMP02" in comps
    assert "WTANK07" in comps


def test_remediate_missing_telemetry():
    proc = FailureLogProcessor()
    raw_log = """
    [2026-02-26 12:00:00] [WARN] PUMP02 auxiliary flow cavitation detected
    [2026-02-26 12:05:00] [CRIT] PUMP02 primary impeller seized. Secondary pump offline.
    """
    initial_events = []
    remediated = proc.remediate_with_missing_components(
        raw_log_content=raw_log,
        current_events=initial_events,
        missing_components=["PUMP02"],
    )
    assert len(remediated) == 2
    assert remediated[0].component_id == "PUMP02"
    assert remediated[1].severity == "[CRIT]"


def test_extract_flag():
    proc = FailureLogProcessor()
    resp1 = {"code": 0, "message": "Gratulacje! Oto flaga: {FLG:NUC_COOL_OK_123}"}
    assert proc.extract_flag(resp1) == "{FLG:NUC_COOL_OK_123}"

    resp2 = "Brak flagi w tej odpowiedzi"
    assert proc.extract_flag(resp2) is None
