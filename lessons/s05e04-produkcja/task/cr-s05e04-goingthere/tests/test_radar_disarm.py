"""Unit tests for OKO radar telemetry parsing, regex fallback, and SHA-1 disarming."""

import hashlib

import pytest

from services.scanner_service import compute_disarm_hash, extract_regex_fallback


def test_compute_disarm_hash() -> None:
    code = "radar_trap_alpha"
    expected = hashlib.sha1(b"radar_trap_alphadisarm").hexdigest()
    assert compute_disarm_hash(code) == expected
    assert len(expected) == 40


def test_extract_regex_fallback_clean_json() -> None:
    payload = '{"frequency": 432, "detectionCode": "oko99"}'
    freq, code = extract_regex_fallback(payload)
    assert freq == 432
    assert code == "oko99"


def test_extract_regex_fallback_distorted_unquoted() -> None:
    payload = "{ frequency: 890, detectionCode: trap_xyz123, status: jammed }"
    freq, code = extract_regex_fallback(payload)
    assert freq == 890
    assert code == "trap_xyz123"


def test_extract_regex_fallback_float_and_noise() -> None:
    payload = '!!! NOISE !!! frequency=105.75 ; detectionCode="code-abc-456" [END]'
    freq, code = extract_regex_fallback(payload)
    assert freq == 105.75
    assert code == "code-abc-456"


def test_disarm_hash_computation_with_spaces() -> None:
    code = "  test_code_123  "
    expected = hashlib.sha1(b"test_code_123disarm").hexdigest()
    assert compute_disarm_hash(code) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        "iT'S   clear!",
        "It's clear!",
        "its clear",
        "It's clear",
        "CLEAR",
        "  clear!  ",
        "It is clear!",
    ],
)
async def test_check_airspace_clear_variations(payload: str) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from services.scanner_service import ScannerService

    mock_gateway = MagicMock()
    mock_gateway.get_scanner_status = AsyncMock(return_value=payload)

    service = ScannerService(gateway=mock_gateway)
    telemetry = await service.check_airspace("dummy_key")

    assert telemetry.is_clear is True
    assert telemetry.frequency is None
    assert telemetry.detection_code is None
