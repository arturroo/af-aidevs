"""Unit tests for ValidationService and pre-flight contract guards."""

import pytest

from schemas import FilesystemFile
from services.validation_service import ValidationService


@pytest.mark.asyncio
async def test_ascii_violation_detected():
    validator = ValidationService()
    files = [
        FilesystemFile(path="/miasta/kraków", content='{"chleb": 10}'),
    ]
    report = await validator.validate_filesystem(files, skip_linguistic=True)
    assert not report.valid
    assert any("ASCII" in err for err in report.errors)


@pytest.mark.asyncio
async def test_json_schema_violation_detected():
    validator = ValidationService()
    files = [
        FilesystemFile(
            path="/miasta/opalino", content='{"chleb": "45 workow"}'
        ),  # string instead of int
    ]
    report = await validator.validate_filesystem(files, skip_linguistic=True)
    assert not report.valid
    assert any("musi byc liczba calkowita" in err for err in report.errors)


@pytest.mark.asyncio
async def test_referential_integrity_violation_detected():
    validator = ValidationService()
    files = [
        FilesystemFile(path="/miasta/opalino", content='{"chleb": 45}'),
        # Person points to non-existent city 'warszawa'
        FilesystemFile(
            path="/osoby/Jan_Kowalski",
            content="Jan Kowalski [Warszawa](/miasta/warszawa)",
        ),
    ]
    report = await validator.validate_filesystem(files, skip_linguistic=True)
    assert not report.valid
    assert any("Integralnosc referencyjna zerwana" in err for err in report.errors)


@pytest.mark.asyncio
async def test_valid_filesystem_pass():
    validator = ValidationService()
    # 8 cities
    city_names = [
        "opalino",
        "domatowo",
        "brudzewo",
        "darzlubie",
        "celbowo",
        "mechowo",
        "puck",
        "karlinkowo",
    ]
    files = [
        FilesystemFile(path=f"/miasta/{c}", content='{"chleb": 45, "woda": 120}')
        for c in city_names
    ]
    # 8 persons
    person_names = [
        ("iga_kapecka", "opalino"),
        ("natan_rams", "domatowo"),
        ("rafal_kisiel", "brudzewo"),
        ("marta_frantz", "darzlubie"),
        ("oskar_radtke", "celbowo"),
        ("eliza_redmann", "mechowo"),
        ("damian_kroll", "puck"),
        ("lena_konkel", "karlinkowo"),
    ]
    for p, c in person_names:
        files.append(
            FilesystemFile(
                path=f"/osoby/{p}",
                content=f"{p.replace('_', ' ').title()} [{c.capitalize()}](/miasta/{c})",
            )
        )

    # Commodities
    files.append(
        FilesystemFile(
            path="/towary/chleb",
            content="[Domatowo](/miasta/domatowo)\n[Opalino](/miasta/opalino)",
        )
    )

    report = await validator.validate_filesystem(files, skip_linguistic=True)
    assert report.valid
    assert len(report.errors) == 0
    assert report.cities_count == 8
    assert report.persons_count == 8
    assert report.commodities_count == 1
