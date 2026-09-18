import asyncio
import concurrent.futures
import json
import logging
from pathlib import Path
from typing import Any

from af_aidevs.utils.prompts import load_system_prompt
from google.adk import Agent, Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

import config
from agents.base import BaseOkoAgent
from schemas import RunTaskResponse
from services.audit_service import AuditService
from services.mcp_service import MCPService
from services.oko_service import OkoService

logger = logging.getLogger("agents.adk")


def _run_coroutine_sync(coro):
    """Safely executes an async coroutine from synchronous tool functions in any event loop context."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()


class ADKOkoAgent(BaseOkoAgent):
    """Google ADK 1.33.0 implementation for task okoeditor using Gemini 3.8 Flash."""

    def __init__(self):
        self.prompt_config = load_system_prompt(
            base_dir=str(Path(__file__).parent.parent)
        )
        self.audit = AuditService(
            dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE
        )
        self.mcp = MCPService()
        self.oko = OkoService(mcp_service=self.mcp, audit_service=self.audit)

    def _create_tools(self, session_id: str, state_tracker: dict[str, Any]):
        oko = self.oko
        mcp = self.mcp
        audit = self.audit

        def call_oko_api(
            action: str, params: dict[str, Any] | None = None, reasoning: str = ""
        ) -> str:
            """Invokes Centrala backdoor API for task 'okoeditor'. Start with action='help', perform the 3 mutations, and finish with action='done'."""
            state_tracker["actions_taken"].append(action)
            try:
                resp = _run_coroutine_sync(
                    oko.call_api(
                        session_id=session_id,
                        action=action,
                        params=params,
                        reasoning=reasoning,
                    )
                )
                if resp.message and "{FLG:" in resp.message:
                    state_tracker["flag"] = resp.message
                return json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception as e:
                logger.error(f"ADK error in call_oko_api action '{action}': {e}")
                return json.dumps(
                    {"status": "error", "action": action, "code": -1, "message": str(e)}
                )

        def fetch_oko_page(page: str = "incydenty", reasoning: str = "") -> str:
            """Covertly fetches a subpage from the operator OKO web panel (e.g. 'incydenty', 'zadania', 'notatki').
            Saves the raw HTML and converted Markdown to workspace, and returns discovered record IDs.
            """
            state_tracker["actions_taken"].append(f"fetch_oko_page_{page}")
            try:
                res = _run_coroutine_sync(
                    oko.fetch_page(
                        session_id=session_id, page=page, reasoning=reasoning
                    )
                )
                return json.dumps(res, ensure_ascii=False)
            except Exception as e:
                logger.error(f"ADK error in fetch_oko_page for '{page}': {e}")
                return json.dumps({"status": "error", "page": page, "message": str(e)})

        def list_workspace_files(path: str = ".", reasoning: str = "") -> str:
            """Lists files and directories in the session workspace."""
            try:
                res = _run_coroutine_sync(
                    mcp.list_files(
                        session_id=session_id, path=path, reasoning=reasoning
                    )
                )
                return json.dumps(res, ensure_ascii=False)
            except Exception as e:
                logger.error(f"ADK error in list_workspace_files for '{path}': {e}")
                return json.dumps({"status": "error", "error": str(e), "files": []})

        def write_workspace_file(file_path: str, content: str, reasoning: str) -> str:
            """Writes artifacts, notes, or execution logs to cr-mcp-workspace."""
            try:
                res = _run_coroutine_sync(
                    mcp.write_file(
                        session_id=session_id,
                        file_path=file_path,
                        content=content,
                        reasoning=reasoning,
                    )
                )
                return json.dumps(res, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        def read_workspace_file(file_path: str, reasoning: str) -> str:
            """Reads a file from cr-mcp-workspace."""
            try:
                res = _run_coroutine_sync(
                    mcp.read_file(
                        session_id=session_id,
                        file_path=file_path,
                        reasoning=reasoning,
                    )
                )
                return json.dumps(res, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        return [
            call_oko_api,
            fetch_oko_page,
            list_workspace_files,
            read_workspace_file,
            write_workspace_file,
        ]

    async def execute(
        self, session_id: str, recursion_limit: int = 30
    ) -> RunTaskResponse:
        logger.info(
            f"Starting Google ADK execution for session {session_id} using {config.GEMINI_MODEL}"
        )

        state_tracker: dict[str, Any] = {
            "flag": None,
            "actions_taken": [],
            "reasoning": "",
        }

        # 1. Audit Session Start
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Initialized Google ADK session {session_id} for task okoeditor",
            step_type="SESSION_START",
            metadata={"model": config.GEMINI_MODEL, "backend": "adk"},
        )

        tools = self._create_tools(session_id=session_id, state_tracker=state_tracker)
        session_service = InMemorySessionService()

        # Build ADK Agent
        agent = Agent(
            model=config.GEMINI_MODEL,
            name="oko_agent",
            instruction=self.prompt_config.system_prompt,
            tools=tools,
        )

        runner = Runner(
            agent=agent,
            session_service=session_service,
            app_name="cr-s04e01-okoeditor",
        )

        user_goal = (
            "Execute covert record adjustments in Centrum Operacyjne OKO via the backdoor API.\n"
            "1. Query call_oko_api with action='help' to discover available commands, queries, and mutation parameters.\n"
            "2. Locate the incident report for Skolwin and reclassify it from vehicle/human sighting to animal activity.\n"
            "3. Locate the operational task for Skolwin, mark it as completed/done, and record in its notes that animals (e.g. beavers / bobry) were sighted.\n"
            "4. Add a diversion incident report detecting human activity near the uninhabited town of Komarowo.\n"
            "5. Verify everything and trigger action='done' to capture the course flag {FLG:...}.\n"
            "Remember: NEVER access the web panel UI directly. Use only call_oko_api."
        )

        try:
            # Create session and execute runner
            session = await session_service.create_session(
                app_name="cr-s04e01-okoeditor", user_id="artur", session_id=session_id
            )
            content = types.Content(
                parts=[types.Part.from_text(text=user_goal)], role="user"
            )

            async for event in runner.run_async(
                session_id=session.id,
                user_id="artur",
                new_message=content,
            ):
                if hasattr(event, "content") and event.content:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            state_tracker["reasoning"] += part.text + "\n"

        except Exception as e:
            logger.error(f"Google ADK execution error: {e}")
            await self.audit.log_event(
                session_id=session_id,
                actor="agent",
                content=f"Google ADK error: {e}",
                step_type="AGENT_ERROR",
                metadata={"error": str(e)},
            )

        flag = state_tracker["flag"]
        safe_flag = "[REDACTED_FLAG]" if flag else "None"
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Completed Google ADK task okoeditor. Flag: {safe_flag}",
            step_type="SESSION_COMPLETE",
            flag=flag,
            metadata={"actions_count": len(state_tracker["actions_taken"])},
        )

        return RunTaskResponse(
            status="success" if flag else "error",
            backend="adk",
            session_id=session_id,
            flag=flag or "[NO_FLAG_OBTAINED]",
            actions_taken=state_tracker["actions_taken"],
            reasoning=state_tracker["reasoning"].strip()
            or "Covert OKO records adjustment sequence executed via ADK.",
        )
