import pytest
from services.safety_guardrail import SafetyGuardrailService


def test_safe_commands_allowed():
    guardrail = SafetyGuardrailService()
    safe_commands = [
        "help",
        "ls -la /opt/firmware/cooler",
        "cat /opt/firmware/cooler/settings.ini",
        "/opt/firmware/cooler/cooler.bin",
        "echo 'db_password=secret' >> /opt/firmware/cooler/settings.ini",
        "pwd",
        "find /home -type f",
    ]
    for cmd in safe_commands:
        allowed, reason = guardrail.validate_command(cmd)
        assert allowed is True, f"Expected safe command '{cmd}' to be allowed, but blocked with: {reason}"
        assert reason is None


@pytest.mark.parametrize(
    "forbidden_cmd",
    [
        "cat /etc/passwd",
        "ls /etc",
        "cat /etc/shadow",
        "ls -la /root",
        "cd /root && ls",
        "cat /proc/cpuinfo",
        "cat /proc/meminfo",
        "ls /proc/",
        "cat ../etc/passwd",
        "cat ../../root/secret",
        "ls ../../../proc",
        "cat /opt/firmware/../../etc/hosts",
        "cat '/etc/passwd'",
        'cat "/root/.bashrc"',
    ],
)
def test_forbidden_system_paths_blocked(forbidden_cmd):
    guardrail = SafetyGuardrailService()
    allowed, reason = guardrail.validate_command(forbidden_cmd)
    assert allowed is False, f"Expected forbidden command '{forbidden_cmd}' to be blocked"
    assert "BLOCKED" in reason


def test_dynamic_gitignore_rules():
    guardrail = SafetyGuardrailService()
    gitignore_content = """
    # Comments should be ignored
    *.log
    secrets/
    id_rsa
    backup.tar.gz
    """
    count = guardrail.update_gitignore_rules(gitignore_content)
    assert count == 4

    # Test blocked patterns
    blocked_commands = [
        "cat server.log",
        "tail -n 20 /opt/app/access.log",
        "cat secrets/api_key.txt",
        "ls secrets",
        "cat id_rsa",
        "tar -czf backup.tar.gz /opt",
    ]
    for cmd in blocked_commands:
        allowed, reason = guardrail.validate_command(cmd)
        assert allowed is False, f"Expected command '{cmd}' to match .gitignore rule and be blocked"
        assert "BLOCKED" in reason
        assert ".gitignore" in reason

    # Safe file that doesn't match rules
    allowed, _ = guardrail.validate_command("cat /opt/firmware/cooler/settings.ini")
    assert allowed is True
