"""Unit tests for ExtractionService helper methods and virtual file building."""

from schemas import (
    CityDemandExtract,
    CoordinatorExtract,
    RawExtractionResult,
    TransactionExtract,
)
from services.extraction_service import ExtractionService, to_ascii


def test_to_ascii_transliteration():
    assert to_ascii("Zażółć gęślą jaźń") == "Zazolc gesla jazn"
    assert to_ascii("Kraków") == "Krakow"
    assert to_ascii("Brudzewo") == "Brudzewo"


def test_build_virtual_files():
    extraction = ExtractionService()
    raw = RawExtractionResult(
        cities=[
            CityDemandExtract(city_name="Opalino", demands={"chleb": 45, "woda": 120}),
            CityDemandExtract(city_name="Domatowo", demands={"makaron": 60}),
        ],
        coordinators=[
            CoordinatorExtract(person_name="Iga Kapecka", city_name="Opalino"),
            CoordinatorExtract(person_name="Natan Rams", city_name="Domatowo"),
        ],
        transactions=[
            TransactionExtract(
                seller_city="Domatowo", commodity="chleb", buyer_city="Opalino"
            ),
            TransactionExtract(
                seller_city="Celbowo", commodity="chleb", buyer_city="Opalino"
            ),
        ],
    )

    files = extraction.build_virtual_files(raw)
    files_by_path = {f.path: f for f in files}

    assert "/miasta/opalino" in files_by_path
    assert '{"chleb": 45, "woda": 120}' in files_by_path["/miasta/opalino"].content

    assert "/osoby/iga_kapecka" in files_by_path
    assert "[Opalino](/miasta/opalino)" in files_by_path["/osoby/iga_kapecka"].content

    assert "/towary/chleb" in files_by_path
    assert "[Celbowo](/miasta/celbowo)" in files_by_path["/towary/chleb"].content
    assert "[Domatowo](/miasta/domatowo)" in files_by_path["/towary/chleb"].content
