from services.router_service import detect_payload_type


def test_detect_sqlite():
    data = b"SQLite format 3\x00some_bytes_here"
    assert detect_payload_type(data) == "application/x-sqlite3"


def test_detect_zip():
    data = b"PK\x03\x04\x14\x00some_zip_header"
    assert detect_payload_type(data) == "application/zip"


def test_detect_png():
    data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    assert detect_payload_type(data) == "image/png"


def test_detect_jpeg():
    data = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    assert detect_payload_type(data) == "image/jpeg"


def test_detect_webp():
    data = b"RIFF\x20\x00\x00\x00WEBPVP8 "
    assert detect_payload_type(data) == "image/webp"


def test_detect_wav():
    data = b"RIFF\x24\x00\x00\x00WAVEfmt "
    assert detect_payload_type(data) == "audio/wav"


def test_detect_mp3():
    data = b"ID3\x03\x00\x00\x00\x00\x00\x00"
    assert detect_payload_type(data) == "audio/mpeg"


def test_detect_json():
    data = b'{"name": "Syjon", "area": 14.85}'
    assert detect_payload_type(data) == "application/json"


def test_detect_markdown():
    data = b"# Section 1\nThis is a report on Domatowo."
    assert detect_payload_type(data) == "text/markdown"


def test_detect_plain_text():
    data = b"Zwykly tekst radiowy bez naglowkow markdown."
    assert detect_payload_type(data) == "text/plain"
