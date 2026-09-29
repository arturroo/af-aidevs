import pytest

from services.temporal_math import (
    compute_sync_ratio,
    get_target_internal_mode,
    parse_date_string,
)
from services.temporal_table import lookup_pwr


def test_sync_ratio_phase1_2238_11_05() -> None:
    ratio = compute_sync_ratio(2238, 11, 5)
    assert ratio == 0.82


def test_sync_ratio_phase2_2026_09_29() -> None:
    ratio = compute_sync_ratio(2026, 9, 29)
    assert ratio == 0.79


def test_sync_ratio_phase3_2024_11_12() -> None:
    ratio = compute_sync_ratio(2024, 11, 12)
    assert ratio == 0.54


def test_internal_mode_resolution() -> None:
    assert get_target_internal_mode(1850) == 1
    assert get_target_internal_mode(1999) == 1
    assert get_target_internal_mode(2000) == 2
    assert get_target_internal_mode(2024) == 2
    assert get_target_internal_mode(2150) == 2
    assert get_target_internal_mode(2151) == 3
    assert get_target_internal_mode(2238) == 3
    assert get_target_internal_mode(2300) == 3
    assert get_target_internal_mode(2301) == 4
    assert get_target_internal_mode(2499) == 4


def test_pwr_lookup_table() -> None:
    assert lookup_pwr(2238) == 91
    assert lookup_pwr(2026) == 28
    assert lookup_pwr(2024) == 19
    assert lookup_pwr(1500) == 3
    assert lookup_pwr(2499) == 97

    with pytest.raises(ValueError):
        lookup_pwr(1499)

    with pytest.raises(ValueError):
        lookup_pwr(2500)


def test_parse_date_string() -> None:
    y, m, d = parse_date_string("2238-11-05")
    assert y == 2238
    assert m == 11
    assert d == 5

    with pytest.raises(ValueError):
        parse_date_string("invalid-date")
