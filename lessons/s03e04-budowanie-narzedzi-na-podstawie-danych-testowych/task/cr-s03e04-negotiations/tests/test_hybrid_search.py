"""Unit tests for HybridSearchService lexical ranking and co-occurrence computation."""

from unittest.mock import MagicMock
import pytest
from schemas import EntitySearchResult, ItemCandidate
from services.hybrid_search_service import HybridSearchService


def test_co_occurrence_calculation():
    """Verify that items sharing cities populate co_occurrence_cities properly."""
    mock_db = MagicMock()
    service = HybridSearchService(db_service=mock_db)

    # Mock search_candidates_for_entity to return candidates with known stocking cities
    cand_cable = ItemCandidate(
        item_code="KBL010",
        item_name="Kabel miedziany 10m",
        hybrid_score=0.9,
        stocking_cities=["Krakow", "Warszawa"],
        co_occurrence_cities=[],
    )
    cand_mast = ItemCandidate(
        item_code="MST002",
        item_name="Maszt rurowy",
        hybrid_score=0.85,
        stocking_cities=["Krakow", "Gdansk"],
        co_occurrence_cities=[],
    )

    def mock_search(entity: str, top_k: int = 3):
        if "kabel" in entity.lower():
            return [cand_cable]
        return [cand_mast]

    service.search_candidates_for_entity = mock_search

    results = service.search_all_entities_with_co_occurrence(["kabel 10m", "maszt"])
    assert len(results) == 2

    # Both cand_cable and cand_mast share "Krakow"
    cable_result = results[0].candidates[0]
    mast_result = results[1].candidates[0]

    assert "Krakow" in cable_result.co_occurrence_cities
    assert "Krakow" in mast_result.co_occurrence_cities
    assert "Warszawa" not in mast_result.co_occurrence_cities
