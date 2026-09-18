import asyncio
import concurrent.futures
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from google.adk import Agent, Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from af_aidevs.utils.prompts import load_system_prompt

import config
from agents.base import BaseNavigationAgent
from schemas import (
    Coordinate,
    RunTaskResponse,
    TerrainMap,
    VehicleSpec,
)
from services.audit_service import AuditService
from services.mcp_service import MCPService
from services.solver_service import SolverService
from services.tool_discovery_service import ToolDiscoveryService
from services.verification_service import VerificationService

logger = logging.getLogger("agents.adk")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


def _run_coroutine_sync(coro):
    """Safely executes an async coroutine from synchronous tool functions in any event loop context."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()


class ADKNavigationAgent(BaseNavigationAgent):
    """Google ADK 1.33.0 implementation for task savethem using Gemini 3.8 Flash."""

    def __init__(self):
        self.prompt_config = load_system_prompt(
            base_dir=str(Path(__file__).parent.parent)
        )
        self.audit = AuditService(
            dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE
        )
        self.mcp = MCPService()
        self.discovery = ToolDiscoveryService(mcp_service=self.mcp)
        self.solver = SolverService()
        self.verification = VerificationService(mcp_service=self.mcp)

    def _create_tools(self, session_id: str, state_tracker: Dict[str, Any]):
        discovery = self.discovery
        solver = self.solver
        verification = self.verification
        mcp = self.mcp
        audit = self.audit

        def search_tools(reasoning: str, query: str) -> str:
            """Searches for available operational domain tools via $AIDEVS_API_TOOLSEARCH using an English query."""
            try:
                tools = _run_coroutine_sync(
                    discovery.search_tools(session_id=session_id, query=query)
                )
                _run_coroutine_sync(
                    audit.log_event(
                        session_id=session_id,
                        actor="tool",
                        content=f"search_tools: '{query}' -> {len(tools)} tools found",
                        step_type="tool_call",
                    )
                )
                return json.dumps(
                    {
                        "count": len(tools),
                        "tools": [
                            {
                                "name": t.name,
                                "endpoint": f"/api/{t.name}",
                                "description": t.description,
                            }
                            for t in tools
                        ],
                        "hint": "Tools discovered! Query them with invoke_remote_tool using their tool_name (e.g. 'maps', 'wehicles').",
                    },
                    ensure_ascii=False,
                )
            except Exception as e:
                logger.error(f"Error in ADK search_tools: {e}")
                return json.dumps({"status": "error", "message": str(e)})

        def invoke_remote_tool(
            reasoning: str,
            tool_name: str,
            query: str,
            endpoint_url: Optional[str] = None,
        ) -> str:
            """Sends a targeted English query to a discovered domain tool via MCP Web Gateway."""
            try:
                res = _run_coroutine_sync(
                    discovery.invoke_remote_tool(
                        session_id=session_id,
                        tool_name=tool_name,
                        query=query,
                        endpoint_url=endpoint_url,
                    )
                )
                _run_coroutine_sync(
                    audit.log_event(
                        session_id=session_id,
                        actor="tool",
                        content=f"invoke_remote_tool: {tool_name} ('{query}')",
                        step_type="tool_call",
                    )
                )
                has_map = discovery.cached_terrain is not None
                known_vehicles = [v.name for v in discovery.cached_vehicles]
                if discovery.cached_foot_spec:
                    known_vehicles.append(discovery.cached_foot_spec.name)

                hint = f"Environment status: map_cached={has_map}, known_vehicles={known_vehicles}. When ready, call plan_and_verify_route."

                return json.dumps(
                    {
                        "tool_name": tool_name,
                        "response": res,
                        "map_cached": has_map,
                        "known_vehicles": known_vehicles,
                        "hint": hint,
                    },
                    ensure_ascii=False,
                )
            except Exception as e:
                logger.error(f"Error in ADK invoke_remote_tool: {e}")
                return json.dumps({"status": "error", "message": str(e)})

        def plan_and_verify_route(
            reasoning: str,
            selected_vehicle: Optional[str] = None,
            vehicle_specs: Optional[List[Dict[str, Any]]] = None,
            terrain_grid: Optional[List[List[str]]] = None,
        ) -> str:
            """Solves the optimal route across the 10x10 terrain grid using Multi-State A* and submits it to Centrala for verification."""
            try:
                # 1. Resolve terrain
                terrain = discovery.cached_terrain
                if terrain_grid and len(terrain_grid) == 10:
                    start_coord = Coordinate(x=0, y=7)
                    dest_coord = Coordinate(x=8, y=4)
                    for r_idx, row in enumerate(terrain_grid):
                        for c_idx, cell in enumerate(row):
                            c_str = str(cell).strip().upper()
                            if c_str == "S":
                                start_coord = Coordinate(x=c_idx, y=r_idx)
                            elif c_str == "G":
                                dest_coord = Coordinate(x=c_idx, y=r_idx)
                    terrain = TerrainMap(grid=terrain_grid, start=start_coord, destination=dest_coord)

                if not terrain:
                    return json.dumps({
                        "status": "error",
                        "message": "Terrain map not loaded. Please invoke the map tool first or pass terrain_grid.",
                    })

                # 2. Resolve vehicles: agent-provided specs take absolute priority
                vehicles: List[VehicleSpec] = []
                foot: Optional[VehicleSpec] = discovery.cached_foot_spec
                if vehicle_specs:
                    for v_dict in vehicle_specs:
                        if isinstance(v_dict, dict):
                            v_name = str(v_dict.get("name", "vehicle")).lower()
                            trav = v_dict.get("traversable_tiles")
                            if not trav:
                                if v_name in {"walk", "foot", "walking"}:
                                    trav = [".", "s", "g", "plain", "road", "grass", "sand", "base", "city", "tree", "forest", "w", "water", "river"]
                                else:
                                    trav = [".", "s", "g", "plain", "road", "grass", "sand", "base", "city"]
                            v_spec = VehicleSpec(
                                name=v_name,
                                fuel_per_move=float(v_dict.get("fuel_per_move", v_dict.get("fuel", 0.0))),
                                food_per_move=float(v_dict.get("food_per_move", v_dict.get("food", 1.0))),
                                speed=float(v_dict.get("speed", 1.0)),
                                traversable_tiles=trav,
                            )
                            if v_name in {"walk", "foot", "walking"}:
                                foot = v_spec
                            vehicles.append(v_spec)
                        elif isinstance(v_dict, VehicleSpec):
                            if v_dict.name.lower() in {"walk", "foot", "walking"}:
                                foot = v_dict
                            vehicles.append(v_dict)
                elif discovery.cached_vehicles:
                    vehicles = discovery.cached_vehicles

                plan = solver.find_best_route(
                    terrain=terrain,
                    vehicles=vehicles,
                    foot_spec=foot,
                    initial_fuel=config.INITIAL_FUEL,
                    initial_food=config.INITIAL_FOOD,
                )

                if not plan or not plan.get("success"):
                    return json.dumps({
                        "status": "failed",
                        "message": "Deterministic solver could not find a path within 10 fuel and 10 food with available vehicles/terrain.",
                    })

                itinerary = plan["itinerary"]
                state_tracker["itinerary"] = itinerary
                state_tracker["fuel_remaining"] = plan["fuel_remaining"]
                state_tracker["food_remaining"] = plan["food_remaining"]
                state_tracker["steps_count"] = plan["steps"]

                verify_res = _run_coroutine_sync(
                    verification.submit_route(session_id=session_id, itinerary=itinerary)
                )

                flag = verify_res.get("flag")
                if flag:
                    state_tracker["flag"] = flag
                    logger.info(f"Course flag captured: {flag}")

                return json.dumps(
                    {
                        "status": "success" if verify_res.get("success") else "failed",
                        "vehicle_used": plan["vehicle"],
                        "steps": plan["steps"],
                        "fuel_remaining": plan["fuel_remaining"],
                        "food_remaining": plan["food_remaining"],
                        "verification_message": verify_res.get("message"),
                        "flag": flag,
                    },
                    ensure_ascii=False,
                )
            except Exception as e:
                logger.error(f"Error in ADK plan_and_verify_route: {e}")
                return json.dumps({"status": "error", "message": str(e)})

        def write_file(file_path: str, content: str, reasoning: str) -> str:
            """Saves a file in cr-mcp-workspace for session persistence."""
            res = _run_coroutine_sync(
                mcp.write_file(
                    session_id=session_id,
                    file_path=file_path,
                    content=content,
                    reasoning=reasoning,
                )
            )
            return json.dumps(res)

        def read_file(file_path: str, reasoning: str) -> str:
            """Reads a file from cr-mcp-workspace."""
            res = _run_coroutine_sync(
                mcp.read_file(session_id=session_id, file_path=file_path, reasoning=reasoning)
            )
            return json.dumps(res)

        return [
            search_tools,
            invoke_remote_tool,
            plan_and_verify_route,
            write_file,
            read_file,
        ]

    async def execute(
        self,
        session_id: str,
        force_refresh: bool = False,
        recursion_limit: int = 30,
    ) -> RunTaskResponse:
        logger.info(
            f"Starting Google ADK execution for session {session_id} using {config.GEMINI_MODEL} (recursion_limit={recursion_limit})"
        )

        state_tracker: Dict[str, Any] = {
            "flag": None,
            "itinerary": [],
            "fuel_remaining": 0.0,
            "food_remaining": 0.0,
            "steps_count": 0,
        }

        # 1. Audit Session Start
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Initialized Google ADK session {session_id} for task savethem (recursion_limit={recursion_limit})",
            step_type="SESSION_START",
            metadata={"model": config.GEMINI_MODEL, "backend": "adk", "recursion_limit": recursion_limit},
        )

        tools = self._create_tools(session_id=session_id, state_tracker=state_tracker)

        agent = Agent(
            name="savethem_navigator",
            model=config.GEMINI_MODEL,
            instruction=self.prompt_config.system_prompt,
            tools=tools,
            generate_content_config=types.GenerateContentConfig(
                temperature=self.prompt_config.temperature or 0.1,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=1024
                    if config.THINKING_LEVEL == "low"
                    else 2048
                ),
            ),
        )

        session_service = InMemorySessionService()
        await session_service.create_session(
            session_id=session_id, app_name="savethem_nav", user_id="artur"
        )
        runner = Runner(agent=agent, session_service=session_service, app_name="savethem_nav")

        user_goal = (
            "You are tasked with safely navigating a human envoy to the survivor settlement of Skolwin across an unknown 10x10 terrain grid.\n"
            "Constraints: initial budget is exactly 10 food portions and 10 fuel units.\n"
            "1. Discover available tools using search_tools.\n"
            "2. Explore the discovered tools with invoke_remote_tool (e.g. tool_name='maps', tool_name='wehicles'). Pay close attention to tool feedback and error messages to refine your queries.\n"
            "3. Extract vehicle specs and terrain layout, then invoke plan_and_verify_route with your findings to compute and verify the optimal route to Skolwin.\n"
            "4. Save your final mission notes and summary in run_notes.md using write_file."
        )

        try:
            user_msg = types.Content(
                role="user", parts=[types.Part.from_text(text=user_goal)]
            )
            step_count = 0
            async for event in runner.run_async(
                session_id=session_id, user_id="artur", new_message=user_msg
            ):
                step_count += 1
                if step_count > recursion_limit:
                    logger.warning(f"ADK runner reached recursion_limit of {recursion_limit}")
                    break
                if hasattr(event, "content") and event.content:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            await self.audit.log_event(
                                session_id=session_id,
                                actor="adk_agent",
                                content=part.text[:500],
                                step_type="agent_thought",
                            )
        except Exception as e:
            logger.error(f"ADK runner error: {e}")
            await self.audit.log_event(
                session_id=session_id,
                actor="agent",
                content=f"ADK error: {e}",
                step_type="AGENT_ERROR",
                metadata={"error": str(e)},
            )

        flag = state_tracker["flag"]
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Completed ADK task savethem. Flag: {flag or 'None'}",
            step_type="SESSION_COMPLETE",
            flag=flag,
            metadata={
                "steps": state_tracker["steps_count"],
                "fuel_remaining": state_tracker["fuel_remaining"],
                "food_remaining": state_tracker["food_remaining"],
            },
        )

        return RunTaskResponse(
            status="success" if flag else "error",
            backend="adk",
            session_id=session_id,
            flag=flag,
            itinerary=state_tracker["itinerary"],
            steps_count=state_tracker["steps_count"],
            fuel_remaining=state_tracker["fuel_remaining"],
            food_remaining=state_tracker["food_remaining"],
            details="Route planned and verified successfully via ADK." if flag else "Could not acquire flag via ADK.",
        )
