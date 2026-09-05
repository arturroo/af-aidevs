import pytest
from services.token_service import TokenService


def test_token_service_local_counting():
    svc = TokenService()
    sample_text = "[2026-02-26 06:04] [CRIT] ECCS8 runaway outlet temp. Protection interlock initiated reactor trip."
    tokens = svc.count_tokens_local(sample_text)
    assert tokens > 10
    assert tokens < 50


def test_token_service_validate_budget():
    svc = TokenService()
    short_text = "Short telemetry log"
    count, is_valid = svc.validate_budget(short_text, max_limit=1500)
    assert is_valid is True
    assert count > 0

    long_text = "word " * 2000
    count_long, is_valid_long = svc.validate_budget(long_text, max_limit=1500)
    assert is_valid_long is False
    assert count_long > 1500
