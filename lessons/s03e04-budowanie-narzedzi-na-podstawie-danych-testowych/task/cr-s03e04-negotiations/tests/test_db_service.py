"""Unit tests for DatabaseService relational set queries and connection handling."""

import sqlite3
import tempfile
from pathlib import Path
import pytest
from services.db_service import DatabaseService


@pytest.fixture
def temp_test_db():
    """Create a temporary SQLite database populated with fixture data."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE cities (code TEXT PRIMARY KEY, name TEXT NOT NULL);")
    cursor.execute("CREATE TABLE items (code TEXT PRIMARY KEY, name TEXT NOT NULL);")
    cursor.execute(
        "CREATE TABLE connections (itemCode TEXT, cityCode TEXT, PRIMARY KEY(itemCode, cityCode));"
    )

    # Insert test cities
    cursor.executemany(
        "INSERT INTO cities (code, name) VALUES (?, ?);",
        [("KRK", "Krakow"), ("WAW", "Warszawa"), ("WRO", "Wroclaw")],
    )

    # Insert test items
    cursor.executemany(
        "INSERT INTO items (code, name) VALUES (?, ?);",
        [("KBL001", "Kabel 10m"), ("MST001", "Maszt"), ("TRB001", "Turbina")],
    )

    # Insert connections:
    # Krakow has KBL001, MST001, TRB001 (all 3!)
    # Warszawa has KBL001, MST001 (only 2)
    # Wroclaw has KBL001 only (only 1)
    cursor.executemany(
        "INSERT INTO connections (itemCode, cityCode) VALUES (?, ?);",
        [
            ("KBL001", "KRK"),
            ("MST001", "KRK"),
            ("TRB001", "KRK"),
            ("KBL001", "WAW"),
            ("MST001", "WAW"),
            ("KBL001", "WRO"),
        ],
    )
    conn.commit()
    conn.close()

    yield db_path

    import gc
    gc.collect()
    try:
        if db_path.exists():
            db_path.unlink()
    except (PermissionError, OSError):
        pass


def test_find_cities_stocking_all_items_three_items(temp_test_db):
    """Verify that only Krakow is returned when all 3 items are queried."""
    db_service = DatabaseService(db_path=temp_test_db)
    results = db_service.find_cities_stocking_all_items(["KBL001", "MST001", "TRB001"])
    assert len(results) == 1
    assert results[0]["name"] == "Krakow"
    assert results[0]["code"] == "KRK"


def test_find_cities_stocking_all_items_two_items(temp_test_db):
    """Verify that both Krakow and Warszawa are returned for 2 common items."""
    db_service = DatabaseService(db_path=temp_test_db)
    results = db_service.find_cities_stocking_all_items(["KBL001", "MST001"])
    assert len(results) == 2
    city_names = [r["name"] for r in results]
    assert "Krakow" in city_names
    assert "Warszawa" in city_names


def test_find_cities_stocking_no_matches(temp_test_db):
    """Verify empty result when querying item combinations that no single city possesses."""
    db_service = DatabaseService(db_path=temp_test_db)
    # Query an item code that doesn't exist
    results = db_service.find_cities_stocking_all_items(["KBL001", "NON_EXISTENT"])
    assert len(results) == 0


def test_get_stocking_cities_for_items(temp_test_db):
    """Verify map of item codes to stocking city names."""
    db_service = DatabaseService(db_path=temp_test_db)
    mapping = db_service.get_stocking_cities_for_items(["KBL001", "MST001"])
    assert len(mapping["KBL001"]) == 3
    assert set(mapping["KBL001"]) == {"Krakow", "Warszawa", "Wroclaw"}
    assert set(mapping["MST001"]) == {"Krakow", "Warszawa"}


def test_extract_content_base64_various_formats():
    """Verify extract_content_base64 handles dict, list of dicts, strings, and wrapped payloads."""
    import base64
    import json
    from services.db_service import extract_content_base64

    b64_sample = base64.b64encode(b"SQLite format 3\x00data").decode("ascii")

    # Format 1: LangChain list of dicts with text containing json
    f1 = [{"type": "text", "text": json.dumps({"status": "success", "content_base64": b64_sample})}]
    assert extract_content_base64(f1) == b64_sample

    # Format 2: Direct dict with text containing json
    f2 = {"type": "text", "text": json.dumps({"status": "success", "content_base64": b64_sample})}
    assert extract_content_base64(f2) == b64_sample

    # Format 3: Direct dict with content_base64
    f3 = {"status": "success", "content_base64": b64_sample}
    assert extract_content_base64(f3) == b64_sample

    # Format 4: Python repr string with single quotes
    f4 = str(f1)
    assert extract_content_base64(f4) == b64_sample

    # Format 5: Direct raw base64 string starting with SQLite format 3 (U1FsaXRl...)
    f5 = b64_sample
    assert extract_content_base64(f5) == b64_sample


@pytest.mark.asyncio
async def test_download_gzip_decompression(monkeypatch, tmp_path):
    """Verify that download_db_from_workspace decompresses gzip-compressed Base64 payloads."""
    import base64
    import gzip
    from unittest.mock import AsyncMock

    uncompressed_sqlite_bytes = b"SQLite format 3\x00" + b"\x00" * 200
    compressed_bytes = gzip.compress(uncompressed_sqlite_bytes, compresslevel=6)
    b64_compressed = base64.b64encode(compressed_bytes).decode("ascii")

    # Mock tool response returning compressed payload
    mock_tool = AsyncMock()
    mock_tool.name = "read_binary_file"
    mock_tool.ainvoke = AsyncMock(
        return_value={"status": "success", "content_base64": b64_compressed}
    )

    # Patch get_all_mcp_tools to return mock_tool
    import services.db_service as dbs
    monkeypatch.setattr(dbs, "get_all_mcp_tools", AsyncMock(return_value=[mock_tool]))

    target_db = tmp_path / "test_decompressed.db"
    db_service = DatabaseService(db_path=target_db)

    await db_service.download_db_from_workspace()

    assert target_db.exists()
    assert target_db.read_bytes() == uncompressed_sqlite_bytes


def test_filter_valid_item_codes(temp_test_db):
    """Verify that filter_valid_item_codes retains only existing codes and rejects noise/invalid codes."""
    db_service = DatabaseService(db_path=temp_test_db)
    # temp_test_db contains: KBL001, MST001, TRB001
    candidates = ["kbl001", "2026Q1", "MST001", "NONEXISTENT", "TRB001", ""]
    valid = db_service.filter_valid_item_codes(candidates)
    assert valid == ["KBL001", "MST001", "TRB001"]


def test_mask_binary_output_nested_structures():
    """Verify recursive masking across dicts, lists, and embedded JSON blocks."""
    import json
    from services.db_service import mask_binary_output

    heavy_b64 = "A" * 1000

    # 1. Direct dict
    d1 = {"content_base64": heavy_b64, "file_path": "test.db"}
    m1 = mask_binary_output(d1)
    assert "<REDACTED_BASE64:" in m1["content_base64"]
    assert m1["file_path"] == "test.db"

    # 2. List of MCP text blocks with embedded JSON (LangChain MCP tool output format)
    raw_mcp_output = [
        {
            "type": "text",
            "text": json.dumps({"status": "success", "content_base64": heavy_b64}),
        }
    ]
    m2 = mask_binary_output(raw_mcp_output)
    assert isinstance(m2, list)
    inner = json.loads(m2[0]["text"])
    assert "<REDACTED_BASE64:" in inner["content_base64"]
    assert inner["status"] == "success"

