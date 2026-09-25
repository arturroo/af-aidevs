from services.validation_service import ValidationService

MOCK_DEMANDS = {
    "opalino": {"chleb": 45, "woda": 120, "mlotek": 6},
    "domatowo": {"makaron": 60, "woda": 150, "lopata": 8},
}

VALID_MANIFEST = [
    {
        "city": "opalino",
        "title": "Dostawa dla Opalino",
        "creatorID": 2,
        "destination": "DEST_OPALINO",
        "signature": "abcdef1234567890abcdef",
        "items": {"chleb": 45, "woda": 120, "mlotek": 6},
    },
    {
        "city": "domatowo",
        "title": "Dostawa dla Domatowo",
        "creatorID": 2,
        "destination": "DEST_DOMATOWO",
        "signature": "abcdef1234567890abcdef",
        "items": {"makaron": 60, "woda": 150, "lopata": 8},
    },
]


def test_valid_manifest():
    report = ValidationService.validate_manifest_data(VALID_MANIFEST, MOCK_DEMANDS)
    assert report.valid is True
    assert len(report.errors) == 0
    assert report.orders_count == 2


def test_missing_city_order():
    incomplete = [VALID_MANIFEST[0]]  # only opalino
    report = ValidationService.validate_manifest_data(incomplete, MOCK_DEMANDS)
    assert report.valid is False
    assert any(
        "Brakujace zamowienia" in err or "domatowo" in err for err in report.errors
    )


def test_item_quantity_discrepancy():
    corrupted = [
        {
            **VALID_MANIFEST[0],
            "items": {"chleb": 44, "woda": 120, "mlotek": 6},  # 44 instead of 45
        },
        VALID_MANIFEST[1],
    ]
    report = ValidationService.validate_manifest_data(corrupted, MOCK_DEMANDS)
    assert report.valid is False
    assert any("chleb" in err and "44" in err for err in report.errors)


def test_missing_signature_and_destination():
    corrupted = [
        {
            **VALID_MANIFEST[0],
            "destination": "",
            "signature": "",
        },
        VALID_MANIFEST[1],
    ]
    report = ValidationService.validate_manifest_data(corrupted, MOCK_DEMANDS)
    assert report.valid is False
    assert any("destination" in err.lower() for err in report.errors)
    assert any("signature" in err.lower() for err in report.errors)


def test_json_string_input():
    import json

    raw_str = json.dumps(VALID_MANIFEST)
    report = ValidationService.validate_manifest_data(raw_str, MOCK_DEMANDS)
    assert report.valid is True
    assert report.orders_count == 2


def test_malformed_json_input():
    report = ValidationService.validate_manifest_data("{invalid_json", MOCK_DEMANDS)
    assert report.valid is False
    assert any("Blad parsowania" in err for err in report.errors)


def test_nested_content_wrapped_manifest():
    import json

    nested = json.dumps({"content": json.dumps(VALID_MANIFEST)})
    report = ValidationService.validate_manifest_data(nested, MOCK_DEMANDS)
    assert report.valid is True
    assert report.orders_count == 2


def test_dict_of_cities_manifest():
    import json

    cities_dict = {
        "opalino": {
            "title": "Dostawa dla Opalino",
            "creatorID": 2,
            "destination": "DEST_OPALINO",
            "signature": "abcdef1234567890abcdef",
            "items": {"chleb": 45, "woda": 120, "mlotek": 6},
        },
        "domatowo": {
            "title": "Dostawa dla Domatowo",
            "creatorID": 2,
            "destination": "DEST_DOMATOWO",
            "signature": "abcdef1234567890abcdef",
            "items": {"makaron": 60, "woda": 150, "lopata": 8},
        },
    }
    report = ValidationService.validate_manifest_data(
        json.dumps(cities_dict), MOCK_DEMANDS
    )
    assert report.valid is True
    assert report.orders_count == 2
