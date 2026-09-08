import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
from langchain.agents import create_agent
from af_aidevs.utils.prompts import load_system_prompt

import config
from schemas import (
    RunTaskResponse,
    ZmailCallRequest,
    GetEmailDetailsRequest,
    VerifyTaskRequest,
)
from services.audit_service import AuditService, BigQueryCallbackHandler
from services.mcp_service import MCPService
from services.mailbox_service import MailboxService
from agents.base import BaseMailboxAgent

logger = logging.getLogger("agents.langchain")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


class LangChainMailboxAgent(BaseMailboxAgent):
    """LangChain 1.2.15 agent implementation on Vertex AI with Gemini 3.8 Flash."""

    def __init__(self):
        self.prompt_config = load_system_prompt(base_dir=str(Path(__file__).parent.parent))
        self.audit = AuditService(dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE)
        self.mcp = MCPService()
        self.mailbox = MailboxService(mcp_service=self.mcp, audit_service=self.audit)

        os.environ["LANGSMITH_PROJECT"] = config.LANGSMITH_PROJECT

        # Gemini 3.8 Flash on Vertex AI with thinking_level="low"
        self.llm = ChatGoogleGenerativeAI(
            model=self.prompt_config.model or config.GEMINI_MODEL,
            temperature=self.prompt_config.temperature,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=self.prompt_config.location or config.GOOGLE_CLOUD_LOCATION,
            vertexai=True,
            thinking_level=config.THINKING_LEVEL,
            include_thoughts=True,
        )

    def _create_domain_tools(self, session_id: str, state_tracker: Dict[str, Any]):
        """Creates hermetic domain tools adhering to contract-first schemas and zero tool stacking."""
        mailbox = self.mailbox

        @tool(args_schema=ZmailCallRequest)
        async def zmail_api_call(action: str, reasoning: str, params: Optional[Dict[str, Any]] = None) -> str:
            """Executes an action (e.g. 'help', 'search', 'getInbox') on the operator's Zmail API."""
            try:
                resp = await mailbox.call_zmail(
                    session_id=session_id,
                    action=action,
                    params=params,
                    reasoning=reasoning,
                )
                return resp.model_dump_json()
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Check action name or parameters against action 'help'."})

        @tool(args_schema=GetEmailDetailsRequest)
        async def get_email_details(message_id: str, reasoning: str) -> str:
            """Fetches the full email message body by message_id, automatically screened through cr-model-armor."""
            try:
                resp = await mailbox.get_email_details(
                    session_id=session_id,
                    message_id=message_id,
                    reasoning=reasoning,
                )
                return resp.model_dump_json()
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Verify message_id exists in mailbox."})

        @tool(args_schema=VerifyTaskRequest)
        async def verify_task(date: str, password: str, confirmation_code: str, reasoning: str) -> str:
            """Submits the extracted date (YYYY-MM-DD), employee password, and confirmation code (SEC-...) to Centrala verification."""
            state_tracker["date"] = date
            state_tracker["password"] = password
            state_tracker["confirmation_code"] = confirmation_code
            try:
                resp = await mailbox.verify_task(
                    session_id=session_id,
                    date=date,
                    password=password,
                    confirmation_code=confirmation_code,
                    reasoning=reasoning,
                )
                if resp.flag:
                    state_tracker["flag"] = resp.flag
                return resp.model_dump_json()
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Check field formats: date=YYYY-MM-DD, code starts with SEC-."})

        # Graceful Tool Error Handling: convert runtime errors into ToolMessages
        tools = [zmail_api_call, get_email_details, verify_task]
        for t in tools:
            t.handle_tool_error = True

        return tools

    async def solve(self, session_id: str, max_iterations: int = 10) -> RunTaskResponse:
        logger.info(f"Starting LangChain solve for session {session_id} using model {config.GEMINI_MODEL}")

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
            content=f"Initialized LangChain session {session_id} with Gemini 3.8 Flash",
            step_type="session_start",
            metadata={"max_iterations": max_iterations, "model": config.GEMINI_MODEL},
        )

        tools = self._create_domain_tools(session_id=session_id, state_tracker=state_tracker)
        bq_callback = BigQueryCallbackHandler(audit_service=self.audit, session_id=session_id)

        # 2. Instantiate LangChain Agent
        agent_graph = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=self.prompt_config.system_prompt,
        )

        user_goal = (
            "Begin mailbox investigation. First inspect the API with help. "
            "Then search for correspondence from Wiktor (proton.me) to determine the attack date, "
            "locate the employee system password in message history, and poll for the security ticket confirmation code. "
            "Verify all three fields with verify_task once found."
        )

        # 3. Execution Loop with Polling
        iterations = 0
        while iterations < max_iterations and not state_tracker["flag"]:
            iterations += 1
            logger.info(f"=== Mailbox Investigation Iteration {iterations}/{max_iterations} ===")

            try:
                await agent_graph.ainvoke(
                    {"messages": [{"role": "user", "content": user_goal}]},
                    config={"callbacks": [bq_callback]},
                )
            except Exception as e:
                logger.error(f"Error during agent invocation (iter {iterations}): {e}")
                await self.audit.log_event(
                    session_id=session_id,
                    actor="agent",
                    content=f"Agent graph execution error: {e}",
                    step_type="agent_error",
                    metadata={"error": str(e), "iteration": iterations},
                )

            if state_tracker["flag"]:
                logger.info(f"Flag captured successfully on iteration {iterations}!")
                break

            # If not yet captured, inform agent of missing elements on next cycle
            user_goal = (
                f"Polling iteration {iterations + 1}. The confirmation code or attack details may have just arrived in the active inbox. "
                "Re-check inbox/search for newly arrived security department notifications or tickets, "
                "read new email bodies, and call verify_task."
            )

        # 4. Save Execution Summary to run_notes.txt
        now_str = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        status_str = "SUCCESS" if state_tracker["flag"] else "FAILED"
        report_content = (
            f"Task: {config.TASK_NAME} (S02E04)\n"
            f"Backend: langchain\n"
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

        # 5. Final Audit Log
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
            backend="langchain",
            notes_file="run_notes.txt",
        )
