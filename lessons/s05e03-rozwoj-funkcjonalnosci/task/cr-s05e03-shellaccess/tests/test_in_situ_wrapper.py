"""Unit tests for the in-situ atomic execution wrapper and cat interception."""

from services.shell_tool import build_in_situ_wrapper, extract_cat_target


def test_wrapper_structure():
    cmd = "grep -i rafal /data/archive.log"
    wrapped = build_in_situ_wrapper(cmd, limit=4000)

    # Check path format
    assert 'TMP="/tmp/_af_aidevs_out_$$"' in wrapped
    # Check command wrapped in subshell
    assert f'({cmd}) > "$TMP" 2>&1' in wrapped
    # Check size check
    assert 'SZ=$(wc -c < "$TMP" 2>/dev/null || echo 0)' in wrapped
    # Check truncation condition
    assert 'if [ "$SZ" -gt 4000 ]; then head -c 4000 "$TMP"' in wrapped
    # Check truncation notice
    assert "[OUTPUT TRUNCATED: $SZ bytes" in wrapped
    # Check fallback cat
    assert 'else cat "$TMP"; fi' in wrapped
    # CRITICAL: Verify rm -f is NOT present!
    assert "rm -f" not in wrapped
    assert "rm " not in wrapped


def test_cat_target_extraction():
    matches = [
        ("cat /data/huge.log", "/data/huge.log"),
        ("cat   /tmp/notes.txt", "/tmp/notes.txt"),
        ('cat "/data/spaces file.txt"', "/data/spaces file.txt"),
        ("cat '/data/single quotes.txt'", "/data/single quotes.txt"),
    ]
    for command, expected_path in matches:
        target = extract_cat_target(command)
        assert target == expected_path, (
            f"Failed for '{command}', expected '{expected_path}', got '{target}'"
        )
