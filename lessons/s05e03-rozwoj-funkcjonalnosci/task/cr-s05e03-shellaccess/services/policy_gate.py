"""Command policy gate enforcing sudo-style allowlists and security boundaries for AI agents."""

import re

ALLOWED_BINARIES = {
    "ls",
    "find",
    "grep",
    "awk",
    "cut",
    "sed",
    "sort",
    "uniq",
    "head",
    "tail",
    "wc",
    "stat",
    "date",
    "echo",
    "jq",
    "pwd",
    "file",
    "which",
    "cat",
    "test",
    "[",
    "true",
    "false",
}

BLACKLISTED_BINARIES = {
    "python",
    "python3",
    "node",
    "ruby",
    "perl",
    "php",
    "zsh",
    "bash",
    "sh",
    "csh",
    "tcsh",
    "fish",
    "rm",
    "mv",
    "chmod",
    "chown",
    "dd",
    "mkfs",
    "kill",
    "pkill",
    "reboot",
    "shutdown",
    "wget",
    "curl",
    "nc",
}

FORK_BOMB_PATTERN = re.compile(r":\s*\(\s*\)\s*\{")


class CommandPolicyGate:
    """Evaluates shell commands against enterprise-grade sudoers allowlists and security rules."""

    @classmethod
    def split_subcommands(cls, cmd: str) -> list[str]:
        """Splits a compound command string by pipes (|, ||) and sequences (;, &&)."""
        tokens = re.split(r"\|\||&&|[|;]", cmd)
        return [t.strip() for t in tokens if t.strip()]

    @classmethod
    def extract_executable(cls, subcmd: str) -> str:
        """Extracts the base executable name from a subcommand line."""
        # Handle variable assignments e.g. FOO=bar ls
        parts = subcmd.split()
        for part in parts:
            if "=" in part and not part.startswith("-"):
                continue
            # Strip path (e.g. /usr/bin/grep -> grep)
            base = part.strip().split("/")[-1]
            return base.lower()
        return ""

    @classmethod
    def validate_command(cls, cmd: str) -> tuple[bool, str]:
        """Validates a command against the security policy.

        Returns:
            (is_allowed, reason)
        """
        if not cmd or not cmd.strip():
            return False, "Command cannot be empty."

        clean_cmd = cmd.strip()

        # Check fork-bomb signatures
        if FORK_BOMB_PATTERN.search(clean_cmd):
            return (
                False,
                "SECURITY VIOLATION: Recursive fork-bomb patterns are strictly forbidden.",
            )

        # Split into subcommands to inspect every step in pipes or sequences
        subcommands = cls.split_subcommands(clean_cmd)
        if not subcommands:
            return False, "Could not parse executable commands."

        for subcmd in subcommands:
            executable = cls.extract_executable(subcmd)
            if not executable:
                continue

            # Check blacklist
            if executable in BLACKLISTED_BINARIES:
                return (
                    False,
                    (
                        f"SECURITY VIOLATION: Binary '{executable}' is strictly prohibited. "
                        "Only standard text diagnostics and search utilities (grep, jq, awk, head) are allowed. "
                        "Scripts in python/zsh/node are forbidden."
                    ),
                )

            # Check allowlist
            if executable not in ALLOWED_BINARIES:
                return (
                    False,
                    (
                        f"POLICY REFUSAL: Binary '{executable}' is not in the allowed sudoers inspection set. "
                        f"Allowed tools: {', '.join(sorted(ALLOWED_BINARIES))}."
                    ),
                )

        return True, ""
