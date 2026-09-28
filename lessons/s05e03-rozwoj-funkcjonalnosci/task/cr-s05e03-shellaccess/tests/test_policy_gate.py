"""Unit tests for CommandPolicyGate."""

from services.policy_gate import CommandPolicyGate


def test_allowed_diagnostics():
    allowed_commands = [
        "ls -la /data",
        "find /data -type f",
        "grep -i rafal /data/archive.log",
        "head -n 25 /data/notes.txt",
        "tail -n 10 /data/events.json",
        "wc -l /data/*",
        "stat /data/archive.log",
        "jq '.entries[]' /data/records.json",
        "cat /data/small.txt",
        "date",
        "echo 'hello world'",
        "pwd",
        "file /data/archive",
    ]
    for cmd in allowed_commands:
        is_allowed, reason = CommandPolicyGate.validate_command(cmd)
        assert is_allowed, (
            f"Expected '{cmd}' to be allowed, but got rejection: {reason}"
        )


def test_allowed_pipelines():
    pipeline = "cat /data/index.txt | grep -i rafal | head -n 5"
    is_allowed, reason = CommandPolicyGate.validate_command(pipeline)
    assert is_allowed, f"Pipeline '{pipeline}' should be allowed, got: {reason}"


def test_blacklisted_binaries():
    forbidden = [
        ("python -c 'print(1)'", "python"),
        ("python3 script.py", "python3"),
        ("node index.js", "node"),
        ("zsh -c 'ls'", "zsh"),
        ("bash script.sh", "bash"),
        ("sh -c 'echo 1'", "sh"),
        ("rm -rf /data", "rm"),
        ("mv /data/a /data/b", "mv"),
        ("chmod 777 /data", "chmod"),
        ("curl http://example.com", "curl"),
        ("wget http://example.com", "wget"),
    ]
    for cmd, binary in forbidden:
        is_allowed, reason = CommandPolicyGate.validate_command(cmd)
        assert not is_allowed, f"Expected '{cmd}' to be rejected!"
        assert "SECURITY VIOLATION" in reason
        assert binary in reason


def test_forbidden_in_pipeline():
    pipeline = "ls /data | python3 process.py"
    is_allowed, reason = CommandPolicyGate.validate_command(pipeline)
    assert not is_allowed
    assert "python3" in reason


def test_fork_bomb_rejection():
    bomb = ":(){ :|:& };:"
    is_allowed, reason = CommandPolicyGate.validate_command(bomb)
    assert not is_allowed
    assert "fork-bomb" in reason
