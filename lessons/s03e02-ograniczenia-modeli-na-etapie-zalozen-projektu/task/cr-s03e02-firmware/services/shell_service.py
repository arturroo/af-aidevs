import asyncio
import logging
import re
from typing import Optional
import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import config
from schemas import ExecuteCommandResponse, RebootVMResponse
from services.safety_guardrail import SafetyGuardrailService

logger = logging.getLogger("services.shell")


class ShellService:
    """Client communicating with the remote HTTP Shell API ($AIDEVS_API_SHELL).

    Equipped with pre-flight safety guardrails, tenacity exponential backoff,
    and ban cooldown sleep-and-retry logic.
    """

    def __init__(
        self,
        guardrail: Optional[SafetyGuardrailService] = None,
        shell_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.guardrail = guardrail or SafetyGuardrailService()
        self.shell_url = shell_url or config.AIDEVS_SHELL_URL
        self.api_key = api_key or config.AIDEVS_API_KEY
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Closes the underlying HTTP client."""
        await self.client.aclose()

    def _extract_cooldown_seconds(self, text: str) -> Optional[int]:
        """Extracts ban cooldown seconds from response error text if present."""
        if not text:
            return None
        match = re.search(r'(?:wait|banned(?:\s+for)?|cooldown)[:\s]*(\d+)\s*(?:seconds|sec|s)?', text, re.I)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                return None
        return None

    async def _post_shell_request(self, command: str) -> httpx.Response:
        """Dispatches raw command to HTTP Shell API with tenacity retry on network blips."""
        payload = {
            "apikey": self.api_key,
            "cmd": command,
        }

        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            stop=stop_after_attempt(5),
            reraise=True,
        ):
            with attempt:
                resp = await self.client.post(self.shell_url, json=payload)
                # Retry on transient 5xx server errors
                if resp.status_code in (500, 502, 503, 504):
                    logger.warning(f"Transient HTTP {resp.status_code} received from shell API. Retrying...")
                    resp.raise_for_status()
                return resp
        raise RuntimeError("Shell request failed after all retries.")

    async def execute_command(self, command: str, reasoning: str = "") -> ExecuteCommandResponse:
        """Executes a shell command on the remote VM after pre-flight safety validation.

        Handles ban cooldowns automatically and dynamically registers discovered .gitignore rules.
        """
        logger.info(f"Requested shell command: '{command}' | Reasoning: {reasoning}")

        # 1. Pre-flight Safety Guardrail check
        allowed, block_reason = self.guardrail.validate_command(command)
        if not allowed:
            logger.warning(f"Command blocked by SafetyGuardrail: {block_reason}")
            return ExecuteCommandResponse(
                output="",
                error=block_reason,
                code=1,
                hint="Target path violates safety policy. Avoid /etc, /root, /proc and gitignored files to prevent VM reset.",
            )

        # 2. Execution with cooldown retry loop
        max_cooldown_retries = 3
        for cooldown_attempt in range(max_cooldown_retries):
            try:
                resp = await self._post_shell_request(command)
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                raw_text = resp.text

                # Check if API returned an error payload or text indicating ban
                output_text = data.get("output") if isinstance(data, dict) and "output" in data else raw_text
                error_text = data.get("error") if isinstance(data, dict) and "error" in data else None
                return_code = data.get("code", 0) if isinstance(data, dict) else (0 if resp.status_code == 200 else resp.status_code)

                combined_output = f"{output_text or ''} {error_text or ''}".strip()

                # Ban cooldown detection
                cooldown_sec = self._extract_cooldown_seconds(combined_output)
                if ("banned" in combined_output.lower() or "wait" in combined_output.lower()) and cooldown_sec:
                    wait_time = cooldown_sec + 1
                    logger.warning(f"Remote firewall ban detected. Sleeping {wait_time}s before retry (attempt {cooldown_attempt + 1}/{max_cooldown_retries})...")
                    await asyncio.sleep(wait_time)
                    continue

                # 3. Dynamic .gitignore discovery
                if ".gitignore" in command and output_text:
                    added = self.guardrail.update_gitignore_rules(output_text)
                    if added > 0:
                        logger.info(f"Ingested {added} rule(s) from .gitignore output into guardrail.")

                hint = None
                if return_code != 0:
                    hint = "Check command syntax or inspect 'help' for supported utilities."

                return ExecuteCommandResponse(
                    output=str(output_text or ""),
                    error=str(error_text) if error_text else None,
                    code=int(return_code),
                    hint=hint,
                )

            except Exception as e:
                logger.error(f"Error executing shell command '{command}': {e}")
                return ExecuteCommandResponse(
                    output="",
                    error=f"Shell execution failed: {str(e)}",
                    code=1,
                    hint="Ensure network connectivity and valid AIDEVS_API_KEY.",
                )

        return ExecuteCommandResponse(
            output="",
            error="Exceeded maximum cooldown retries due to persistent firewall bans.",
            code=1,
            hint="Wait and execute 'reboot_vm' if environment is locked.",
        )

    async def reboot_vm(self, reasoning: str = "") -> RebootVMResponse:
        """Issues an emergency reset command to restore the VM back to its initial snapshot."""
        logger.info(f"Emergency VM reboot requested. Reasoning: {reasoning}")
        try:
            # Send reset command to shell API
            res = await self.execute_command(command="reset", reasoning=reasoning)
            if res.code == 0 or "reset" in res.output.lower() or "snapshot" in res.output.lower():
                return RebootVMResponse(
                    status="success",
                    message="VM snapshot reset successfully initiated.",
                    hint="Run 'help' to begin clean exploration.",
                )
            else:
                return RebootVMResponse(
                    status="partial",
                    message=f"Reset command dispatched. Output: {res.output}",
                    hint="Check filesystem status with 'ls'.",
                )
        except Exception as e:
            logger.error(f"Failed to reset VM: {e}")
            return RebootVMResponse(
                status="error",
                message=f"Reboot failed: {str(e)}",
                hint="Retry after cooldown period.",
            )
