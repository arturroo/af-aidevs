"""Unit tests for the Local Pydantic Verification Gate and date calculation."""

from schemas import RafalDiscoveryExtraction, RendezvousPayload
from services.orchestrator import compute_rendezvous


def test_standard_date_subtraction():
    extraction = RafalDiscoveryExtraction(
        discovery_date="2024-05-15",
        city="Warszawa",
        latitude=52.2297,
        longitude=21.0122,
        reasoning="Test record",
    )
    rendezvous = compute_rendezvous(extraction)
    assert rendezvous.date == "2024-05-14"
    assert rendezvous.city == "Warszawa"
    assert rendezvous.latitude == 52.2297
    assert rendezvous.longitude == 21.0122


def test_leap_year_month_boundary():
    # 2024 is a leap year; 2024-03-01 minus 1 day must be 2024-02-29
    extraction = RafalDiscoveryExtraction(
        discovery_date="2024-03-01",
        city="Grudziadz",
        latitude=53.4837,
        longitude=18.7533,
        reasoning="Leap year edge case",
    )
    rendezvous = compute_rendezvous(extraction)
    assert rendezvous.date == "2024-02-29"


def test_non_leap_year_month_boundary():
    # 2023 is not a leap year; 2023-03-01 minus 1 day must be 2023-02-28
    extraction = RafalDiscoveryExtraction(
        discovery_date="2023-03-01",
        city="Grudziadz",
        latitude=53.4837,
        longitude=18.7533,
    )
    rendezvous = compute_rendezvous(extraction)
    assert rendezvous.date == "2023-02-28"


def test_year_boundary():
    # 2024-01-01 minus 1 day must be 2023-12-31
    extraction = RafalDiscoveryExtraction(
        discovery_date="2024-01-01",
        city="Torun",
        latitude=53.0138,
        longitude=18.5984,
    )
    rendezvous = compute_rendezvous(extraction)
    assert rendezvous.date == "2023-12-31"


def test_rendezvous_json_serialization():
    rendezvous = RendezvousPayload(
        date="2024-02-29",
        city="Grudziadz",
        latitude=53.4837,
        longitude=18.7533,
    )
    json_str = rendezvous.model_dump_json()
    assert '"date":"2024-02-29"' in json_str
    assert '"city":"Grudziadz"' in json_str
    assert '"latitude":53.4837' in json_str
    assert '"longitude":18.7533' in json_str
