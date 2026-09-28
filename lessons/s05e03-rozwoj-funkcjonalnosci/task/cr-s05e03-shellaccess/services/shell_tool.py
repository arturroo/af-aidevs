"""Shell execution tool for AI agents featuring in-situ remote wrapping and cat interception."""

import logging
import re

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config import config
from services.centrala_service import CentralaService
from services.policy_gate import CommandPolicyGate

logger = logging.getLogger("services.shell_tool")

CAT_COMMAND_REGEX = re.compile(
    r"^\s*cat\s+(?:[\"']([^\"']+)[\"']|([^\s\|;&><]+))", re.IGNORECASE
)


def extract_cat_target(command: str) -> str | None:
    """Extracts filepath from a cat command, supporting quoted and unquoted paths."""
    match = CAT_COMMAND_REGEX.match(command)
    if match:
        return (match.group(1) or match.group(2) or "").strip()
    return None


def build_in_situ_wrapper(cmd: str, limit: int = config.OUTPUT_CHAR_LIMIT) -> str:
    """Wraps an exploratory command into an atomic bash compound execution with remote truncation."""
    wrapper = (
        f'TMP="/tmp/_af_aidevs_out_$$"; '
        f'({cmd}) > "$TMP" 2>&1; '
        f'SZ=$(wc -c < "$TMP" 2>/dev/null || echo 0); '
        f'if [ "$SZ" -gt {limit} ]; then '
        f'head -c {limit} "$TMP"; '
        f'echo -e "\\n\\n[OUTPUT TRUNCATED: $SZ bytes. Use grep or head to narrow down]"; '
        f'else cat "$TMP"; fi'
    )
    return wrapper


class CentralaShellTool:
    """Orchestrates shell execution with sudo-style policy checks and proactive file guards."""

    def __init__(self, centrala_service: CentralaService) -> None:
        self.centrala_service = centrala_service

    async def _check_file_size(self, filepath: str) -> int:
        """Executes a lightweight size check on the remote host for a specific file path."""
        size_cmd = f'stat -c %s "{filepath}" 2>/dev/null || wc -c < "{filepath}" 2>/dev/null || echo 0'
        try:
            resp = await self.centrala_service.execute_shell_direct(size_cmd)
            raw = resp.message.strip().split()[-1]
            return int(raw)
        except Exception as e:
            logger.debug(f"Pre-flight file size check failed for {filepath}: {e}")
            return 0

    async def execute_agent_command(self, cmd: str) -> str:
        """Validates and executes an agent shell command."""
        clean_cmd = cmd.strip()

        # 1. Evaluate Sudo-Style Command Policy Gate
        is_allowed, reason = CommandPolicyGate.validate_command(clean_cmd)
        if not is_allowed:
            logger.warning(
                f"CommandPolicyGate rejected command '{clean_cmd[:80]}': {reason}"
            )
            return f"[POLICY REFUSAL: {reason}]"

        # 2. Proactive `cat` Interception Guard
        filepath = extract_cat_target(clean_cmd)
        if filepath:
            file_size = await self._check_file_size(filepath)
            if file_size >= config.OUTPUT_CHAR_LIMIT:
                return (
                    f"[SECURITY GUARD: Direct 'cat' blocked. Target file '{filepath}' is {file_size} bytes "
                    f"(limit: {config.OUTPUT_CHAR_LIMIT}B). Please use 'head -n 25 {filepath}' or "
                    f"'grep -i <pattern> {filepath}' to inspect safely.]"
                )

        # 3. Dispatch validated command to Centrala
        resp = await self.centrala_service.execute_shell_direct(clean_cmd)

        # 4. Client-Side Safety Cap
        raw_output = resp.message or ""
        if len(raw_output) > config.OUTPUT_CHAR_LIMIT:
            raw_output = (
                raw_output[: config.OUTPUT_CHAR_LIMIT]
                + f"\n\n[CLIENT TRUNCATED AT {config.OUTPUT_CHAR_LIMIT} CHARACTERS. Total: {len(resp.message)} chars]"
            )

        return raw_output


class ExecuteShellInput(BaseModel):
    cmd: str = Field(
        ...,
        description="The UNIX shell command to execute on the remote Linux host (e.g. 'ls -la /data', 'grep -i rafal /data/incidents.log').",
        examples=["ls -la /data", "grep -i rafal /data/archive.log | head -n 10"],
    )


def create_execute_shell_tool(shell_tool: CentralaShellTool):
    """Factory creating a LangChain tool bound to the CentralaShellTool instance."""

    @tool("execute_shell", args_schema=ExecuteShellInput)
    async def execute_shell(cmd: str) -> str:
        """Executes a UNIX shell command on the remote Linux host.
        Use this tool to explore directories, inspect files, and search logs using grep, jq, head, awk, etc.
        Destructive commands (rm, mv, chmod) and script interpreters (python, zsh) are strictly prohibited.
        """
        return await shell_tool.execute_agent_command(cmd)

    return execute_shell
