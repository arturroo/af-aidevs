import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from af_aidevs.utils.prompts import load_system_prompt
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

import config
from agents.base import BaseDomatowoAgent
from schemas import (
    CalculateRouteInput,
    DomatowoApiInput,
    RunTaskResponse,
    WorkspaceFileReadInput,
    WorkspaceFileWriteInput,
)
from services.audit_service import AuditCallbackHandler, AuditService
from services.domatowo_service import DomatowoService
from services.mcp_service import MCPService
from services.navigation_service import NavigationService

logger = logging.getLogger("agents.langchain")


class LangChainDomatowoAgent(BaseDomatowoAgent):
    """LangChain 1.2.15 implementation for task domatowo using Gemini 3.8 Flash."""

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

        os.environ["LANGSMITH_PROJECT"] = config.LANGSMITH_PROJECT

        self.llm = ChatGoogleGenerativeAI(
            model=self.prompt_config.model or config.GEMINI_MODEL,
            temperature=self.prompt_config.temperature or 0.1,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=self.prompt_config.location or config.GOOGLE_CLOUD_LOCATION,
            vertexai=True,
            thinking_level=config.THINKING_LEVEL,
            include_thoughts=False,
        )

    def _create_tools(self, session_id: str, state_tracker: dict[str, Any]):
        ds = self.domatowo

        @tool(args_schema=DomatowoApiInput)
        async def call_domatowo_api(
            action: str,
            params: dict[str, Any] | None = None,
            reasoning: str = "",
        ) -> str:
            """Universal meta-tool for executing actions against Centrala's Domatowo API. All commands returned by the API help manual (e.g. reset, getMap, create, move, inspect, etc.) MUST be executed through this tool using action='<command_name>' and params={...}. Do NOT attempt raw HTTP requests or undeclared tool names."""
            params_dict = params or {}
            state_tracker["actions_taken"].append(f"api_{action}")
            try:
                resp = await ds.execute_action(
                    session_id=session_id,
                    action=action,
                    params=params_dict,
                    reasoning=reasoning,
                )
                flag = ds.extracted_flags.get(session_id)
                if flag:
                    state_tracker["flag"] = flag
                survivor_tile = ds.survivor_tile.get(session_id)
                if survivor_tile:
                    state_tracker["survivor_tile"] = survivor_tile
                return json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error in call_domatowo_api for action '{action}': {e}")
                return json.dumps(
                    {"status": "error", "action": action, "message": str(e)}
                )

        @tool(args_schema=CalculateRouteInput)
        async def calculate_route(
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
                logger.error(f"Error in calculate_route from '{origin}': {e}")
                return json.dumps({"status": "error", "message": str(e)})

        @tool(args_schema=WorkspaceFileReadInput)
        async def read_mission_workspace(
            file_path: str = "todos.md",
            reasoning: str = "",
        ) -> str:
            """Reads a file (e.g. todos.md) from the persistent session workspace."""
            state_tracker["actions_taken"].append(f"read_ws_{file_path}")
            try:
                resp = await ds.read_workspace_file(
                    session_id=session_id, file_path=file_path, reasoning=reasoning
                )
                return json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error in read_mission_workspace '{file_path}': {e}")
                return json.dumps(
                    {"status": "error", "file_path": file_path, "message": str(e)}
                )

        @tool(args_schema=WorkspaceFileWriteInput)
        async def update_mission_workspace(
            file_path: str = "todos.md",
            content: str = "",
            reasoning: str = "",
        ) -> str:
            """Writes or updates a file (e.g. todos.md) in the persistent session workspace."""
            state_tracker["actions_taken"].append(f"update_ws_{file_path}")
            try:
                resp = await ds.update_workspace_file(
                    session_id=session_id,
                    file_path=file_path,
                    content=content,
                    reasoning=reasoning,
                )
                return json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error in update_mission_workspace '{file_path}': {e}")
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
        """Executes autonomous search and rescue operation in Domatowo using LangChain."""
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
        callback = AuditCallbackHandler(audit_service=self.audit, session_id=session_id)

        agent = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=self.prompt_config.system_prompt,
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
            result = await agent.ainvoke(
                {"messages": [("user", initial_user_prompt)]},
                config={
                    "callbacks": [callback],
                    "recursion_limit": recursion_limit,
                },
            )

            # Look for flag in state_tracker or service or result
            flag = state_tracker.get("flag") or self.domatowo.extracted_flags.get(
                session_id
            )
            if not flag and "messages" in result:
                for msg in reversed(result["messages"]):
                    content_str = str(getattr(msg, "content", ""))
                    match = re.search(r"(\{FLG:[^\}]+\})", content_str)
                    if match:
                        flag = match.group(1)
                        break

            survivor_tile = state_tracker.get(
                "survivor_tile"
            ) or self.domatowo.survivor_tile.get(session_id)
            ap_spent = self.domatowo.get_ap_spent(session_id)
            success = bool(flag)

            return RunTaskResponse(
                success=success,
                flag=flag,
                backend_used="langchain",
                ap_spent=ap_spent,
                final_location=survivor_tile,
                error=None
                if success
                else "Mission finished without capturing course flag.",
            )
        except Exception as e:
            logger.error(f"LangChain execution error: {e}", exc_info=True)
            return RunTaskResponse(
                success=False,
                flag=state_tracker.get("flag")
                or self.domatowo.extracted_flags.get(session_id),
                backend_used="langchain",
                ap_spent=self.domatowo.get_ap_spent(session_id),
                final_location=state_tracker.get("survivor_tile"),
                error=str(e),
            )
