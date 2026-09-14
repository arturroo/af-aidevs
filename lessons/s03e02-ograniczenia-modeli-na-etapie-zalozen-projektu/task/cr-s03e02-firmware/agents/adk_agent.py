import asyncio
import concurrent.futures
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from google.adk import Agent, Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from af_aidevs.utils.prompts import load_system_prompt

import config
from agents.base import BaseFirmwareAgent
from schemas import RunTaskResponse
from services.audit_service import AuditService
from services.mcp_service import MCPService
from services.shell_service import ShellService
from services.verification_service import VerificationService

logger = logging.getLogger("agents.adk")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


def _run_coroutine_sync(coro):
    """Safely executes an async coroutine from synchronous tool functions in any event loop context."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()


class ADKFirmwareAgent(BaseFirmwareAgent):
    """Google ADK implementation (google-adk==1.33.0) with Gemini 3.8 Flash and BigQuery telemetry."""

    def __init__(self):
        self.prompt_config = load_system_prompt(base_dir=str(Path(__file__).parent.parent))
        self.audit = AuditService(dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE)
        self.mcp = MCPService()
        self.shell = ShellService()
        self.verification = VerificationService()

    def _create_tools(self, session_id: str, state_tracker: Dict[str, Any]):
        shell = self.shell
        verification = self.verification

        def execute_shell_command(command: str, reasoning: str) -> str:
            """Executes a non-interactive shell command on the remote ECCS controller VM."""
            try:
                res = _run_coroutine_sync(shell.execute_command(command=command, reasoning=reasoning))
                match = re.search(r'(ECCS-[a-zA-Z0-9]{40})', res.output)
                if match:
                    token = match.group(1)
                    state_tracker["confirmation_code"] = token
                    logger.info(f"ADK captured runtime token: {token}")

                return json.dumps(res.model_dump())
            except Exception as e:
                logger.error(f"Error in ADK execute_shell_command: {e}")
                return json.dumps({
                    "output": "",
                    "error": str(e),
                    "code": 1,
                    "hint": "Check command syntax or inspect 'help'.",
                })

        def reboot_vm(reasoning: str) -> str:
            """Issues an emergency reset to restore the VM back to its initial snapshot."""
            try:
                res = _run_coroutine_sync(shell.reboot_vm(reasoning=reasoning))
                return json.dumps(res.model_dump())
            except Exception as e:
                return json.dumps({
                    "status": "error",
                    "message": str(e),
                    "hint": "Retry reset command if needed.",
                })

        def submit_confirmation(confirmation_code: str, reasoning: str) -> str:
            """Submits the extracted ECCS confirmation code to Centrala verification server."""
            state_tracker["confirmation_code"] = confirmation_code
            try:
                res = _run_coroutine_sync(verification.verify_confirmation_code(
                    confirmation_code=confirmation_code, reasoning=reasoning
                ))
                if res.flag:
                    state_tracker["flag"] = res.flag
                    logger.info(f"ADK captured flag: {res.flag}")
                return json.dumps(res.model_dump())
            except Exception as e:
                return json.dumps({
                    "status": "error",
                    "code": -1,
                    "flag": None,
                    "message": str(e),
                    "hint": "Verify token format and network connectivity.",
                })

        return [execute_shell_command, reboot_vm, submit_confirmation]

    async def solve(self, session_id: str, max_iterations: int = 15) -> RunTaskResponse:
        logger.info(f"Starting Google ADK solve for session {session_id} using model {config.GEMINI_MODEL}")

        state_tracker: Dict[str, Any] = {
            "flag": None,
            "confirmation_code": None,
            "steps_executed": 0,
        }

        # 1. Audit Session Start
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Initialized Google ADK session {session_id} with Gemini 3.8 Flash",
            step_type="SESSION_START",
            metadata={"max_iterations": max_iterations, "model": config.GEMINI_MODEL},
        )

        tools = self._create_tools(session_id=session_id, state_tracker=state_tracker)

        root_agent = Agent(
            name="firmware_agent",
            model=self.prompt_config.model or config.GEMINI_MODEL,
            instruction=self.prompt_config.system_prompt,
            tools=tools,
        )

        session_service = InMemorySessionService()
        runner = Runner(
            app_name="s03e02_adk",
            agent=root_agent,
            session_service=session_service,
            auto_create_session=True,
        )

        initial_goal = (
            "Diagnose and remediate the Emergency Core Cooling System (ECCS) controller firmware failure.\n"
            "Step 1: Run 'help' to identify available custom shell commands and text manipulation tools.\n"
            "Step 2: Inspect authorized directories (/home/, /opt/) to find database/controller credentials.\n"
            "Step 3: Run /opt/firmware/cooler/cooler.bin and examine error diagnostics.\n"
            "Step 4: Inspect and edit /opt/firmware/cooler/settings.ini using discovered text editing utilities.\n"
            "Step 5: Run /opt/firmware/cooler/cooler.bin again, extract confirmation code (ECCS-[a-zA-Z0-9]{40}).\n"
            "Step 6: Submit code via submit_confirmation tool to acquire the lesson flag.\n"
            "REMEMBER: Never access /etc, /root, /proc or .gitignore files to avoid firewall bans."
        )

        loop_counter = 0
        while loop_counter < max_iterations and not state_tracker["flag"]:
            loop_counter += 1
            state_tracker["steps_executed"] = loop_counter
            logger.info(f"=== Google ADK Iteration {loop_counter}/{max_iterations} ===")

            new_message = types.Content(role="user", parts=[types.Part.from_text(text=initial_goal)])

            try:
                event_count = 0
                async for event in runner.run_async(
                    user_id="default_user",
                    session_id=session_id,
                    new_message=new_message,
                ):
                    event_count += 1
                    if event_count > 30:
                        break
            except Exception as e:
                logger.error(f"Error during ADK runner execution (iteration {loop_counter}): {e}")
                await self.audit.log_event(
                    session_id=session_id,
                    actor="agent",
                    content=f"ADK runner error: {e}",
                    step_type="AGENT_ERROR",
                    metadata={"error": str(e), "iteration": loop_counter},
                )

            if state_tracker["flag"]:
                logger.info(f"ADK flag captured successfully on iteration {loop_counter}!")
                break

            if state_tracker.get("confirmation_code") and not state_tracker.get("flag"):
                initial_goal = (
                    f"Iteration {loop_counter + 1}: Found confirmation token: {state_tracker['confirmation_code']}. "
                    "Submit it immediately via submit_confirmation tool to capture the flag."
                )
            else:
                initial_goal = (
                    f"Iteration {loop_counter + 1}: Task not yet completed. "
                    "Review previous command outputs. Check if cooler.bin returned an error message. "
                    "Ensure settings.ini contains the correct database/connection parameters discovered from the VM."
                )

        # 2. Save Execution Summary to run_notes.txt
        now_str = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        status_str = "SUCCESS" if state_tracker["flag"] else "FAILED"
        report_content = (
            f"Task: {config.TASK_NAME} (S03E02)\n"
            f"Backend: adk\n"
            f"Session ID: {session_id}\n"
            f"Timestamp: {now_str}\n"
            f"Status: {status_str}\n"
            f"Steps Executed: {state_tracker['steps_executed']}\n"
            f"Confirmation Code: {state_tracker.get('confirmation_code') or 'NOT_FOUND'}\n"
            f"Flag: {state_tracker.get('flag') or 'NOT_CAPTURED'}\n"
        )
        await self.mcp.write_file(session_id=session_id, file_path="run_notes.txt", content=report_content)

        # 3. Final Audit Log
        await self.audit.log_event(
            session_id=session_id,
            actor="agent",
            content=f"Task completed with status {status_str}",
            step_type="SESSION_END",
            flag=state_tracker.get("flag"),
            metadata={
                "status": status_str,
                "steps_executed": state_tracker["steps_executed"],
                "confirmation_code": state_tracker.get("confirmation_code"),
            },
        )

        return RunTaskResponse(
            status="success" if state_tracker["flag"] else "failed",
            session_id=session_id,
            backend="adk",
            confirmation_code=state_tracker.get("confirmation_code"),
            flag=state_tracker.get("flag"),
            steps_executed=state_tracker["steps_executed"],
            details=f"Diagnostic finished with status: {status_str}.",
        )
