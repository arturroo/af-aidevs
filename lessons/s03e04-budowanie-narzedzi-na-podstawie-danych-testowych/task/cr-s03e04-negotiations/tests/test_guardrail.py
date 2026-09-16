"""Unit tests for response guardrails and byte envelope enforcement."""

import pytest
from services.response_guardrail import (
    enforce_byte_envelope,
    get_byte_length,
    validate_byte_bounds,
)


def test_valid_response_bounds():
    """Verify normal length responses pass through untouched."""
    valid_text = "Zidentyfikowano: Kabel miedziany 10m (kod: KBL010)."
    assert validate_byte_bounds(valid_text) is True
    assert enforce_byte_envelope(valid_text) == valid_text


def test_short_response_padding():
    """Verify strings shorter than 4 bytes trigger fallback."""
    too_short = "Ok"
    assert len(too_short.encode("utf-8")) == 2
    assert validate_byte_bounds(too_short) is False
    guarded = enforce_byte_envelope(too_short)
    assert len(guarded.encode("utf-8")) >= 4
    assert guarded == "Brak danych."


def test_long_response_truncation():
    """Verify strings longer than 500 bytes are gracefully truncated with ellipsis."""
    long_text = "To jest bardzo długa informacja techniczna o komponentach turbiny wiatrowej. " * 15
    raw_bytes_len = len(long_text.encode("utf-8"))
    assert raw_bytes_len > 500
    assert validate_byte_bounds(long_text) is False

    guarded = enforce_byte_envelope(long_text)
    guarded_len = len(guarded.encode("utf-8"))
    assert guarded_len <= 500
    assert guarded_len >= 4
    assert guarded.endswith("...")


def test_polish_diacritics_byte_safety():
    """Verify multi-byte UTF-8 Polish characters do not produce decoding errors."""
    polish_sentence = "Kraków, Łódź, Poznań, Gdańsk, Wrocław i Bydgoszcz posiadają komponenty."
    guarded = enforce_byte_envelope(polish_sentence)
    assert "Kraków" in guarded
    assert validate_byte_bounds(guarded) is True


def test_tool_request_list_coercion():
    """Verify ToolRequest seamlessly coerces list and dict payloads to normalized string."""
    from schemas import ToolRequest

    # List of codes from Centrala LLM tool caller
    req_list = ToolRequest(params=["VEHCKW", "TDRG36", "TRB500"])
    assert req_list.params == "VEHCKW, TDRG36, TRB500"

    # String input
    req_str = ToolRequest(params="VEHCKW, TDRG36")
    assert req_str.params == "VEHCKW, TDRG36"

    # Dict input
    req_dict = ToolRequest(params={"items": ["A", "B"]})
    assert "items" in req_dict.params

