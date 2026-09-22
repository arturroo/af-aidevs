import asyncio
import concurrent.futures
import json
import logging
import re
from pathlib import Path
from typing import Any

from af_aidevs.utils.prompts import load_system_prompt
from google.adk import Agent, Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

import config
from agents.base import BaseDomatowoAgent
from schemas import RunTaskResponse
from services.audit_service import AuditService
from services.domatowo_service import DomatowoService
from services.mcp_service import MCPService
from services.navigation_service import NavigationService

logger = logging.getLogger("agents.adk")


def _run_coroutine_sync(coro):
    """Safely executes an async coroutine from synchronous tool functions in any event loop context."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()


class ADKDomatowoAgent(BaseDomatowoAgent):
    """Google ADK 1.33.0 implementation for task domatowo using Gemini 3.8 Flash."""

    def __init__(self):
        self.prompt_config = load_system_prompt(
            base_dir=str(Path(__file__).parent.parent)
        )
        self.audit = AuditService(
            dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE
        )
        self.mcp = MCPService()
        self.nav = NavigationService()
        self.domatowo = DomatowoService(
            audit_service=self.audit,
            mcp_service=self.mcp,
            navigation_service=self.nav,
        )

    def _create_tools(self, session_id: str, state_tracker: dict[str, Any]):
        ds = self.domatowo

        def call_domatowo_api(
            action: str,
            params: dict[str, Any] | None = None,
            reasoning: str = "",
        ) -> str:
            """Universal meta-tool for executing actions against Centrala's Domatowo API. All commands returned by the API help manual (e.g. reset, getMap, create, move, inspect, etc.) MUST be executed through this tool using action='<command_name>' and params={...}. Do NOT attempt raw HTTP requests or undeclared tool names."""
            params_dict = params or {}
            state_tracker["actions_taken"].append(f"api_{action}")
            try:
                resp = _run_coroutine_sync(
                    ds.execute_action(
                        session_id=session_id,
                        action=action,
                        params=params_dict,
                        reasoning=reasoning,
                    )
                )
                flag = ds.extracted_flags.get(session_id)
                if flag:
                    state_tracker["flag"] = flag
                survivor_tile = ds.survivor_tile.get(session_id)
                if survivor_tile:
                    state_tracker["survivor_tile"] = survivor_tile
                return json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception as e:
                logger.error(f"ADK error in call_domatowo_api action '{action}': {e}")
                return json.dumps(
                    {"status": "error", "action": action, "message": str(e)}
                )

        def calculate_route(
            origin: str,
            destination: str | None = None,
            target_symbol: str | None = None,
            unit_type: str = "transporter",
            reasoning: str = "",
        ) -> str:
            """Calculates the minimal AP route for a transporter (road-only) or scout (foot patrol), returning drop-off recommendations."""
            state_tracker["actions_taken"].append(
                f"route_{origin}_to_{destination or target_symbol}"
            )
            try:
                resp = ds.calculate_route(
                    origin=origin,
                    destination=destination,
                    target_symbol=target_symbol,
                    unit_type=unit_type,
                    reasoning=reasoning,
                )
                return json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception as e:
                logger.error(f"ADK error in calculate_route: {e}")
                return json.dumps({"status": "error", "message": str(e)})

        def read_mission_workspace(
            file_path: str = "todos.md",
            reasoning: str = "",
        ) -> str:
            """Reads a file (e.g. todos.md) from the persistent session workspace."""
            state_tracker["actions_taken"].append(f"read_ws_{file_path}")
            try:
                resp = _run_coroutine_sync(
                    ds.read_workspace_file(
                        session_id=session_id, file_path=file_path, reasoning=reasoning
                    )
                )
                return json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception as e:
                logger.error(f"ADK error in read_mission_workspace: {e}")
                return json.dumps(
                    {"status": "error", "file_path": file_path, "message": str(e)}
                )

        def update_mission_workspace(
            file_path: str = "todos.md",
            content: str = "",
            reasoning: str = "",
        ) -> str:
            """Writes or updates a file (e.g. todos.md) in the persistent session workspace."""
            state_tracker["actions_taken"].append(f"update_ws_{file_path}")
            try:
                resp = _run_coroutine_sync(
                    ds.update_workspace_file(
                        session_id=session_id,
                        file_path=file_path,
                        content=content,
                        reasoning=reasoning,
                    )
                )
                return json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception as e:
                logger.error(f"ADK error in update_mission_workspace: {e}")
                return json.dumps(
                    {"status": "error", "file_path": file_path, "message": str(e)}
                )

        return [
            call_domatowo_api,
            calculate_route,
            read_mission_workspace,
            update_mission_workspace,
        ]

    async def execute(
        self, session_id: str, recursion_limit: int = 40
    ) -> RunTaskResponse:
        """Executes autonomous search and rescue operation in Domatowo using Google ADK."""
        state_tracker: dict[str, Any] = {
            "actions_taken": [],
            "flag": None,
            "survivor_tile": None,
        }

        # Initialize workspace with initial todos.md
        initial_todos = (
            "# Mission Checklist - Domatowo\n"
            "- [ ] 1. Discover API capabilities and parameters by calling help\n"
            "- [ ] 2. Reset board state, action points (300 AP), and queue via reset\n"
            "- [ ] 3. Retrieve tactical map (getMap) and identify BLOK_3P targets\n"
            "- [ ] 4. Deploy transporter with scouts\n"
            "- [ ] 5. Navigate to candidate cluster and disembark scout\n"
            "- [ ] 6. Perform clockwise sweep & inspect tiles\n"
            "- [ ] 7. Call helicopter evacuation\n\n"
            "## Tactical Search State\n"
            "- Checkpoint ID: `cp-00-init`\n"
            "- Step: 0\n"
            "- Last Action: Initialized\n"
            "- AP Remaining Estimate: 300 / 300\n"
            "- Visited Clusters: []\n"
            "- Inspected Tiles: []\n"
            "- Current Position: Base\n"
            "- Survivor Found: False\n"
        )
        await self.domatowo.update_workspace_file(
            session_id=session_id,
            file_path="todos.md",
            content=initial_todos,
            reasoning="Bootstrapping session workspace with initial mission checklist.",
        )

        tools = self._create_tools(session_id=session_id, state_tracker=state_tracker)

        agent = Agent(
            name="adk_domatowo_agent",
            model=self.prompt_config.model or config.GEMINI_MODEL,
            instruction=self.prompt_config.system_prompt,
            tools=tools,
        )

        session_service = InMemorySessionService()
        runner = Runner(
            agent=agent,
            session_service=session_service,
            max_iterations=recursion_limit,
        )

        initial_user_prompt = (
            f"Commander, commence Operation Domatowo (Session: {session_id}).\n"
            "The radio distress transmission has been verified. A wounded, armed partisan is hiding in one of the city's highest residential blocks (BLOK_3P).\n"
            "You have an absolute ceiling of 300 Action Points (AP).\n"
            "Step 1: Call `call_domatowo_api(action='help')` to discover API capabilities.\n"
            "Step 2: Save the discovered commands, parameters, and descriptions into `api_manual.md` in your workspace.\n"
            "Step 3: Read `todos.md` and execute each mission checklist step sequentially using `call_domatowo_api`.\n"
            "Step 4: Update `todos.md` at key tactical milestones and return the final extracted course flag."
        )

        await self.audit.log_event(
            session_id=session_id,
            actor="user",
            content=initial_user_prompt,
            step_type="mission_start",
        )

        try:
            # Create session and run turn
            session = await session_service.create_session(
                session_id=session_id, user_id="commander"
            )

            user_msg = types.Content(
                role="user",
                parts=[types.Part.from_text(text=initial_user_prompt)],
            )

            async for event in runner.run_async(
                user_id="commander",
                session_id=session.id,
                message=user_msg,
            ):
                if hasattr(event, "content") and event.content:
                    text_out = str(event.content)
                    match = re.search(r"(\{FLG:[^\}]+\})", text_out)
                    if match:
                        state_tracker["flag"] = match.group(1)

            flag = state_tracker.get("flag") or self.domatowo.extracted_flags.get(
                session_id
            )
            survivor_tile = state_tracker.get(
                "survivor_tile"
            ) or self.domatowo.survivor_tile.get(session_id)
            ap_spent = self.domatowo.get_ap_spent(session_id)
            success = bool(flag)

            return RunTaskResponse(
                success=success,
                flag=flag,
                backend_used="adk",
                ap_spent=ap_spent,
                final_location=survivor_tile,
                error=None
                if success
                else "ADK Mission completed without capturing course flag.",
            )
        except Exception as e:
            logger.error(f"Google ADK execution error: {e}", exc_info=True)
            return RunTaskResponse(
                success=False,
                flag=state_tracker.get("flag")
                or self.domatowo.extracted_flags.get(session_id),
                backend_used="adk",
                ap_spent=self.domatowo.get_ap_spent(session_id),
                final_location=state_tracker.get("survivor_tile"),
                error=str(e),
            )
