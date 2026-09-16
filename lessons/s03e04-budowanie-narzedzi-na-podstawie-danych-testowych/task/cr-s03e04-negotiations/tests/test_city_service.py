"""Unit tests for CityService (Tool 2) execution and deterministic formatting."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from schemas import Tool2PreFlightOutput
from services.city_service import CityService


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_city_service_no_codes_fail_fast(monkeypatch):
    """Verify fail-fast error returned when no 6-character codes are extracted."""
    mock_db = MagicMock()
    mock_db.filter_valid_item_codes.return_value = []
    mock_caller = MagicMock()
    mock_caller.extract_item_codes = AsyncMock(
        return_value=Tool2PreFlightOutput(
            reasoning="Brak kodów w zapytaniu",
            item_codes=[],
        )
    )

    city_service = CityService(db_service=mock_db)
    monkeypatch.setattr("services.city_service.get_tool_caller", lambda backend: mock_caller)

    output = await city_service.find_cities(
        user_query="hej potrzebuję części do turbiny",
        session_id="test_sess",
    )
    assert "Nie znaleziono 6-znakowych kodów" in output
    assert "search_item_in_catalog" in output
    assert len(output.encode("utf-8")) <= 500
    assert len(output.encode("utf-8")) >= 4


@pytest.mark.asyncio
async def test_city_service_matching_cities_formatted(monkeypatch):
    """Verify deterministic formatting when matching cities are found via fast-path regex."""
    mock_db = MagicMock()
    mock_db.filter_valid_item_codes.return_value = ["KBL010", "MST002", "TRB500"]
    mock_db.find_cities_stocking_all_items.return_value = [
        {"name": "Krakow", "code": "M2Z8LP"},
        {"name": "Wroclaw", "code": "H6Y1CB"},
    ]

    mock_caller = MagicMock()
    mock_caller.extract_item_codes = AsyncMock()

    city_service = CityService(db_service=mock_db)
    monkeypatch.setattr("services.city_service.get_tool_caller", lambda backend: mock_caller)

    output = await city_service.find_cities(
        user_query="KBL010, MST002, TRB500",
        session_id="test_sess",
    )
    assert "Krakow (M2Z8LP)" in output
    assert "Wroclaw (H6Y1CB)" in output
    assert "wszystkie 3 przedmioty" in output
    assert len(output.encode("utf-8")) <= 500
    assert len(output.encode("utf-8")) >= 4
    # LLM extract_item_codes was bypassed because fast-path succeeded
    mock_caller.extract_item_codes.assert_not_called()


@pytest.mark.asyncio
async def test_city_service_llm_fallback_when_regex_empty(monkeypatch):
    """Verify fallback to LLM when fast-path finds no valid codes."""
    mock_db = MagicMock()
    mock_db.filter_valid_item_codes.return_value = []
    mock_db.find_cities_stocking_all_items.return_value = [
        {"name": "Gdansk", "code": "G8D2X1"}
    ]

    mock_caller = MagicMock()
    mock_caller.extract_item_codes = AsyncMock(
        return_value=Tool2PreFlightOutput(
            reasoning="Ekstrakcja LLM",
            item_codes=["FLW12V"],
        )
    )

    city_service = CityService(db_service=mock_db)
    monkeypatch.setattr("services.city_service.get_tool_caller", lambda backend: mock_caller)

    output = await city_service.find_cities(
        user_query="potrzebuję sprawdzić wariant flw12v",
        session_id="test_sess",
    )
    assert "Gdansk (G8D2X1)" in output
    mock_caller.extract_item_codes.assert_called_once()
