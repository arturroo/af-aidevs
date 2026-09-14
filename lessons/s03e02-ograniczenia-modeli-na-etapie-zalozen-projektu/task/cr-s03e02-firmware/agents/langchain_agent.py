import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from af_aidevs.utils.prompts import load_system_prompt

import config
from agents.base import BaseFirmwareAgent
from schemas import (
    ExecuteCommandInput,
    RebootVMInput,
    RunTaskResponse,
    VerifySolutionInput,
)
from services.audit_service import AuditService, BigQueryCallbackHandler
from services.mcp_service import MCPService
from services.shell_service import ShellService
from services.verification_service import VerificationService

logger = logging.getLogger("agents.langchain")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


class LangChainFirmwareAgent(BaseFirmwareAgent):
    """LangChain 1.2.15 implementation for ECCS firmware diagnostics using Gemini 3.8 Flash."""

    def __init__(self):
        self.prompt_config = load_system_prompt(base_dir=str(Path(__file__).parent.parent))
        self.audit = AuditService(dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE)
        self.mcp = MCPService()
        self.shell = ShellService()
        self.verification = VerificationService()

        os.environ["LANGSMITH_PROJECT"] = config.LANGSMITH_PROJECT

        # Initialize Gemini 3.8 Flash on Vertex AI with thinking_level="low"
        self.llm = ChatGoogleGenerativeAI(
            model=self.prompt_config.model or config.GEMINI_MODEL,
            temperature=self.prompt_config.temperature or 0.1,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=self.prompt_config.location or config.GOOGLE_CLOUD_LOCATION,
            vertexai=True,
            thinking_level=config.THINKING_LEVEL,
            include_thoughts=True,
        )

    def _create_tools(self, session_id: str, state_tracker: Dict[str, Any]):
        shell = self.shell
        verification = self.verification

        @tool(args_schema=ExecuteCommandInput)
        async def execute_shell_command(command: str, reasoning: str) -> str:
            """Executes a non-interactive shell command on the remote ECCS controller VM."""
            try:
                res = await shell.execute_command(command=command, reasoning=reasoning)
                # Check for runtime token pattern ECCS-[a-zA-Z0-9]{40}
                match = re.search(r'(ECCS-[a-zA-Z0-9]{40})', res.output)
                if match:
                    token = match.group(1)
                    state_tracker["confirmation_code"] = token
                    logger.info(f"Captured runtime token: {token}")

                return json.dumps(res.model_dump())
            except Exception as e:
                logger.error(f"Error in execute_shell_command tool: {e}")
                return json.dumps({
                    "output": "",
                    "error": str(e),
                    "code": 1,
                    "hint": "Check command syntax or inspect 'help'.",
                })

        @tool(args_schema=RebootVMInput)
        async def reboot_vm(reasoning: str) -> str:
            """Issues an emergency reset to restore the VM back to its initial snapshot."""
            try:
                res = await shell.reboot_vm(reasoning=reasoning)
                return json.dumps(res.model_dump())
            except Exception as e:
                return json.dumps({
                    "status": "error",
                    "message": str(e),
                    "hint": "Retry reset command if needed.",
                })

        @tool(args_schema=VerifySolutionInput)
        async def submit_confirmation(confirmation_code: str, reasoning: str) -> str:
            """Submits the extracted ECCS confirmation code to Centrala verification server."""
            state_tracker["confirmation_code"] = confirmation_code
            try:
                res = await verification.verify_confirmation_code(
                    confirmation_code=confirmation_code, reasoning=reasoning
                )
                if res.flag:
                    state_tracker["flag"] = res.flag
                    logger.info(f"Flag captured successfully: {res.flag}")
                return json.dumps(res.model_dump())
            except Exception as e:
                return json.dumps({
                    "status": "error",
                    "code": -1,
                    "flag": None,
                    "message": str(e),
                    "hint": "Verify token format and network connectivity.",
                })

        tools = [execute_shell_command, reboot_vm, submit_confirmation]

        # Graceful Tool Error Handling: convert runtime errors into ToolMessages
        for t in tools:
            t.handle_tool_error = True

        return tools

    async def solve(self, session_id: str, max_iterations: int = 15) -> RunTaskResponse:
        logger.info(f"Starting LangChain solve for session {session_id} using model {config.GEMINI_MODEL}")

        state_tracker: Dict[str, Any] = {
            "flag": None,
            "confirmation_code": None,
            "steps_executed": 0,
        }

        # 1. Audit Session Start
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Initialized LangChain session {session_id} with Gemini 3.8 Flash",
            step_type="SESSION_START",
            metadata={"max_iterations": max_iterations, "model": config.GEMINI_MODEL},
        )

        tools = self._create_tools(session_id=session_id, state_tracker=state_tracker)
        bq_callback = BigQueryCallbackHandler(audit_service=self.audit, session_id=session_id)

        # 2. Instantiate LangChain Agent
        agent_graph = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=self.prompt_config.system_prompt,
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
            logger.info(f"=== ECCS Firmware Diagnostic Iteration {loop_counter}/{max_iterations} ===")

            try:
                await agent_graph.ainvoke(
                    {"messages": [{"role": "user", "content": initial_goal}]},
                    config={"callbacks": [bq_callback]},
                )
            except Exception as e:
                logger.error(f"Error during LangChain invocation (iteration {loop_counter}): {e}")
                await self.audit.log_event(
                    session_id=session_id,
                    actor="agent",
                    content=f"Agent execution error: {e}",
                    step_type="AGENT_ERROR",
                    metadata={"error": str(e), "iteration": loop_counter},
                )

            if state_tracker["flag"]:
                logger.info(f"Flag captured successfully on iteration {loop_counter}!")
                break

            # If token found but not verified yet
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

        # 3. Save Execution Summary to run_notes.txt
        now_str = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        status_str = "SUCCESS" if state_tracker["flag"] else "FAILED"
        report_content = (
            f"Task: {config.TASK_NAME} (S03E02)\n"
            f"Backend: langchain\n"
            f"Session ID: {session_id}\n"
            f"Timestamp: {now_str}\n"
            f"Status: {status_str}\n"
            f"Steps Executed: {state_tracker['steps_executed']}\n"
            f"Confirmation Code: {state_tracker.get('confirmation_code') or 'NOT_FOUND'}\n"
            f"Flag: {state_tracker.get('flag') or 'NOT_CAPTURED'}\n"
        )
        await self.mcp.write_file(session_id=session_id, file_path="run_notes.txt", content=report_content)

        # 4. Final Audit Log
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
            backend="langchain",
            confirmation_code=state_tracker.get("confirmation_code"),
            flag=state_tracker.get("flag"),
            steps_executed=state_tracker["steps_executed"],
            details=f"Diagnostic finished with status: {status_str}.",
        )
