from decimal import Decimal

from agents.synthesis_subagent import format_city_area


def test_rounding_half_up_boundary():
    # 14.845 with ROUND_HALF_UP MUST round to 14.85, NOT 14.84
    assert format_city_area("14.845") == "14.85"
    assert format_city_area(14.845) == "14.85"
    assert format_city_area(Decimal("14.845")) == "14.85"


def test_rounding_already_two_decimals():
    assert format_city_area("12.34") == "12.34"
    assert format_city_area(12.34) == "12.34"


def test_rounding_single_decimal():
    assert format_city_area("12.3") == "12.30"
    assert format_city_area(12.3) == "12.30"


def test_rounding_integer():
    assert format_city_area("15") == "15.00"
    assert format_city_area(15) == "15.00"


def test_rounding_comma_decimal():
    assert format_city_area("14,845") == "14.85"
    assert format_city_area("12,34") == "12.34"


def test_rounding_with_units():
    assert format_city_area("14.845 km²") == "14.85"
    assert format_city_area("14.85 km2") == "14.85"
