import os
import json
import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo

from google.adk import Agent, Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from af_aidevs.utils.prompts import load_system_prompt

import config
from schemas import RunTaskResponse
from services.audit_service import AuditService
from services.mcp_service import MCPService
from services.mailbox_service import MailboxService
from agents.base import BaseMailboxAgent

logger = logging.getLogger("agents.adk")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


def _run_coroutine_sync(coro):
    """Safely executes an async coroutine from synchronous tool functions in any event loop context."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()


class ADKMailboxAgent(BaseMailboxAgent):
    """Google ADK implementation (google-adk==1.33.0) with Gemini 3.8 Flash and BigQuery telemetry."""

    def __init__(self):
        self.prompt_config = load_system_prompt(base_dir=str(Path(__file__).parent.parent))
        self.audit = AuditService(dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE)
        self.mcp = MCPService()
        self.mailbox = MailboxService(mcp_service=self.mcp, audit_service=self.audit)

    def _create_adk_tools(self, session_id: str, state_tracker: Dict[str, Any]):
        mailbox = self.mailbox

        def zmail_api_call(action: str, reasoning: str, params: Optional[dict] = None) -> str:
            """Calls the compromised operator Zmail API with action (e.g. 'help', 'search', 'getInbox') and optional params."""
            try:
                resp = _run_coroutine_sync(
                    mailbox.call_zmail(
                        session_id=session_id,
                        action=action,
                        params=params,
                        reasoning=reasoning,
                    )
                )
                return resp.model_dump_json()
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Check action name against action 'help'."})

        def get_email_details(message_id: str, reasoning: str) -> str:
            """Fetches full email message body screened through cr-model-armor."""
            try:
                resp = _run_coroutine_sync(
                    mailbox.get_email_details(
                        session_id=session_id,
                        message_id=message_id,
                        reasoning=reasoning,
                    )
                )
                return resp.model_dump_json()
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Verify message_id exists in inbox."})

        def verify_task(date: str, password: str, confirmation_code: str, reasoning: str) -> str:
            """Submits attack date (YYYY-MM-DD), password, and confirmation code (SEC-...) to Centrala verification."""
            state_tracker["date"] = date
            state_tracker["password"] = password
            state_tracker["confirmation_code"] = confirmation_code
            try:
                resp = _run_coroutine_sync(
                    mailbox.verify_task(
                        session_id=session_id,
                        date=date,
                        password=password,
                        confirmation_code=confirmation_code,
                        reasoning=reasoning,
                    )
                )
                if resp.flag:
                    state_tracker["flag"] = resp.flag
                return resp.model_dump_json()
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Check formats: date=YYYY-MM-DD, code starts with SEC-."})

        return [zmail_api_call, get_email_details, verify_task]

    async def solve(self, session_id: str, max_iterations: int = 10) -> RunTaskResponse:
        logger.info(f"Starting Google ADK solve for session {session_id} using model {config.GEMINI_MODEL}")

        state_tracker: Dict[str, Any] = {
            "flag": None,
            "date": None,
            "password": None,
            "confirmation_code": None,
        }

        # 1. Audit Session Start
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Initialized Google ADK session {session_id} with Gemini 3.8 Flash",
            step_type="session_start",
            metadata={"max_iterations": max_iterations, "model": config.GEMINI_MODEL},
        )

        tools = self._create_adk_tools(session_id=session_id, state_tracker=state_tracker)

        root_agent = Agent(
            name="mailbox_agent",
            model=self.prompt_config.model or config.GEMINI_MODEL,
            instruction=self.prompt_config.system_prompt,
            tools=tools,
        )

        session_service = InMemorySessionService()
        runner = Runner(
            app_name="s02e04_adk",
            agent=root_agent,
            session_service=session_service,
            auto_create_session=True,
        )

        initial_goal = (
            "Begin mailbox investigation. First inspect the API with help. "
            "Then search for correspondence from Wiktor (proton.me) to determine the attack date, "
            "locate the employee system password in message history, and poll for the security ticket confirmation code. "
            "Verify all three fields with verify_task once found."
        )

        iterations = 0
        while iterations < max_iterations and not state_tracker["flag"]:
            iterations += 1
            logger.info(f"=== Google ADK Iteration {iterations}/{max_iterations} ===")

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
                logger.error(f"Error during ADK runner execution (iter {iterations}): {e}")
                await self.audit.log_event(
                    session_id=session_id,
                    actor="agent",
                    content=f"ADK runner error: {e}",
                    step_type="agent_error",
                    metadata={"error": str(e), "iteration": iterations},
                )

            if state_tracker["flag"]:
                logger.info(f"Flag captured successfully on iteration {iterations}!")
                break

            initial_goal = (
                f"Polling iteration {iterations + 1}. The confirmation code or attack details may have just arrived in the active inbox. "
                "Re-check inbox/search for newly arrived security department notifications or tickets, "
                "read new email bodies, and call verify_task."
            )

        # 2. Save Execution Summary to run_notes.txt
        now_str = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        status_str = "SUCCESS" if state_tracker["flag"] else "FAILED"
        report_content = (
            f"Task: {config.TASK_NAME} (S02E04)\n"
            f"Backend: adk\n"
            f"Session ID: {session_id}\n"
            f"Timestamp: {now_str}\n"
            f"Iterations: {iterations}\n"
            f"Status: {status_str}\n"
            f"Date: {state_tracker.get('date') or 'NOT_FOUND'}\n"
            f"Password: {state_tracker.get('password') or 'NOT_FOUND'}\n"
            f"Confirmation Code: {state_tracker.get('confirmation_code') or 'NOT_FOUND'}\n"
            f"Flag: {state_tracker.get('flag') or 'NOT_CAPTURED'}\n"
        )
        await self.mcp.write_file(session_id=session_id, file_path="run_notes.txt", content=report_content)

        # 3. Final Audit Log
        await self.audit.log_event(
            session_id=session_id,
            actor="agent",
            content=f"Task completed with status {status_str}",
            step_type="final_answer",
            flag="[REDACTED_FLAG]" if state_tracker["flag"] else None,
            metadata={"status": status_str, "iterations": iterations, "tracker": state_tracker},
        )

        return RunTaskResponse(
            status="success" if state_tracker["flag"] else "failed",
            session_id=session_id,
            flag=state_tracker["flag"],
            date=state_tracker.get("date"),
            password=state_tracker.get("password"),
            confirmation_code=state_tracker.get("confirmation_code"),
            iterations=iterations,
            backend="adk",
            notes_file="run_notes.txt",
        )
