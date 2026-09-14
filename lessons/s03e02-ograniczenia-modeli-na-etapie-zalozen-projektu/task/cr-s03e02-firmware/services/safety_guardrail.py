import fnmatch
import logging
import posixpath
import re
import shlex
from typing import List, Optional, Set, Tuple

logger = logging.getLogger("services.safety_guardrail")


class SafetyGuardrailService:
    """Client-side pre-flight interceptor preventing remote firewall bans.

    Blocks commands attempting to inspect /etc, /root, /proc/ (including relative path traversals)
    and dynamically enforces .gitignore patterns discovered during VM exploration.
    """

    FORBIDDEN_ROOTS: Tuple[str, ...] = ("etc", "root", "proc")

    # Regex detecting explicit references to forbidden paths anywhere in command line
    FORBIDDEN_PATH_PATTERN = re.compile(
        r"""
        (?:^|[\s"'\`=|&;<>()])      # delimiter or command boundary
        (?:\.\./+)*                 # optional relative parent traversals (../, ../../)
        /?(?:etc|root|proc)         # forbidden directory root
        (?:[/\\s"'\`=|&;<>()$]|$)   # boundary or child path separator
        """,
        re.VERBOSE | re.IGNORECASE,
    )

    def __init__(self):
        self.gitignore_rules: Set[str] = set()

    def update_gitignore_rules(self, gitignore_content: str, base_dir: str = "") -> int:
        """Parses .gitignore content, adds rules to active blacklist cache, and returns count of added rules."""
        added_count = 0
        for line in gitignore_content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Strip leading/trailing slashes for consistent fnmatch matching
            normalized_pattern = stripped.strip("/")
            if base_dir and not stripped.startswith("/"):
                normalized_pattern = f"{base_dir.strip('/')}/{normalized_pattern}"

            if normalized_pattern not in self.gitignore_rules:
                self.gitignore_rules.add(normalized_pattern)
                added_count += 1

        if added_count > 0:
            logger.info(f"Updated dynamic .gitignore cache with {added_count} new rule(s). Total rules: {len(self.gitignore_rules)}")
        return added_count

    def _extract_path_tokens(self, command: str) -> List[str]:
        """Extracts potential path and filename tokens from the command line."""
        tokens: List[str] = []
        try:
            tokens = shlex.split(command, posix=True)
        except Exception:
            # Fallback split on whitespace and delimiters if shlex fails on non-standard syntax
            tokens = re.split(r'[\s|&;<>]+', command)

        extracted: List[str] = []
        for token in tokens:
            cleaned = token.strip().strip("'\"`")
            # If token is a flag (e.g. -la, --file=foo), strip flag prefix
            if cleaned.startswith("-") and "=" in cleaned:
                cleaned = cleaned.split("=", 1)[1].strip("'\"`")
            elif cleaned.startswith("-"):
                continue

            if cleaned:
                extracted.append(cleaned)
        return extracted

    def is_forbidden_system_path(self, path_str: str) -> Tuple[bool, Optional[str]]:
        """Checks if a path string targets /etc, /root, /proc or traverses into them."""
        # 1. Regex check on raw string
        if self.FORBIDDEN_PATH_PATTERN.search(path_str):
            return True, f"Direct reference to forbidden system directory detected in path: '{path_str}'"

        # 2. Posix path normalization check
        normalized = posixpath.normpath(path_str).lstrip("/")
        parts = normalized.split("/")
        if parts and parts[0].lower() in self.FORBIDDEN_ROOTS:
            return True, f"Normalized path '{normalized}' attempts to access forbidden root '/{parts[0]}'"

        # 3. Traversal component check
        if any(part.lower() in self.FORBIDDEN_ROOTS for part in parts):
            # E.g. var/log/../../etc or similar embedded traversal
            for i, part in enumerate(parts):
                if part.lower() in self.FORBIDDEN_ROOTS and (i == 0 or parts[0] in ("..", ".")):
                    return True, f"Traversing into forbidden directory: '/{part}'"

        return False, None

    def matches_gitignore_cache(self, path_str: str) -> Tuple[bool, Optional[str]]:
        """Checks if a path string matches any dynamically discovered .gitignore rule."""
        if not self.gitignore_rules:
            return False, None

        normalized = posixpath.normpath(path_str).strip("/")
        basename = posixpath.basename(normalized)
        parts = normalized.split("/")

        for rule in self.gitignore_rules:
            # 1. Exact or glob match on full path
            if fnmatch.fnmatch(normalized, rule) or fnmatch.fnmatch(normalized, f"*/{rule}"):
                return True, f"Path '{path_str}' matches active .gitignore rule: '{rule}'"
            # 2. Match on child files within ignored directory
            if fnmatch.fnmatch(normalized, f"{rule}/*") or fnmatch.fnmatch(normalized, f"*/{rule}/*"):
                return True, f"Path '{path_str}' is inside ignored directory matching .gitignore rule: '{rule}'"
            if rule in parts:
                return True, f"Path '{path_str}' traverses ignored directory matching .gitignore rule: '{rule}'"
            # 3. Check filename basename
            if fnmatch.fnmatch(basename, rule):
                return True, f"Filename '{basename}' matches active .gitignore rule: '{rule}'"

        return False, None

    def validate_command(self, command: str) -> Tuple[bool, Optional[str]]:
        """Validates command against static blacklist and dynamic gitignore rules.

        Returns:
            (True, None) if command is permitted.
            (False, reason_message) if command is blocked.
        """
        if not command or not command.strip():
            return False, "Command cannot be empty."

        cmd_trimmed = command.strip()

        # 1. Broad regex scan across full raw command line
        if self.FORBIDDEN_PATH_PATTERN.search(cmd_trimmed):
            reason = "Command contains references to forbidden system directories (/etc, /root, /proc)."
            logger.warning(f"[Guardrail Blocked] {reason} Command: {cmd_trimmed}")
            return False, f"BLOCKED: {reason} Action prohibited by safety policy."

        # 2. Token-level analysis
        tokens = self._extract_path_tokens(cmd_trimmed)
        for token in tokens:
            # Check forbidden system paths
            is_forbidden, reason = self.is_forbidden_system_path(token)
            if is_forbidden:
                logger.warning(f"[Guardrail Blocked] {reason} Token: {token} in command: {cmd_trimmed}")
                return False, f"BLOCKED: {reason}. Action prohibited by safety policy."

            # Check dynamic .gitignore rules
            matches_gi, gi_reason = self.matches_gitignore_cache(token)
            if matches_gi:
                logger.warning(f"[Guardrail Blocked] {gi_reason} in command: {cmd_trimmed}")
                return False, f"BLOCKED: {gi_reason}. Action prohibited by safety policy."

        return True, None
