import os
import json
import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
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
from services.drone_service import DroneService
from agents.base import BaseDroneAgent

logger = logging.getLogger("agents.adk")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


def _run_coroutine_sync(coro):
    """Safely executes an async coroutine from synchronous tool functions in any event loop context."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()


class ADKDroneAgent(BaseDroneAgent):
    """Google ADK implementation (google-adk==1.33.0) with Gemini 3.8 Flash and BigQuery telemetry."""

    def __init__(self):
        self.prompt_config = load_system_prompt(base_dir=str(Path(__file__).parent.parent))
        self.audit = AuditService(dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE)
        self.mcp = MCPService()
        self.drone = DroneService(mcp_service=self.mcp, audit_service=self.audit)

    def _create_adk_tools(self, session_id: str, state_tracker: Dict[str, Any]):
        drone = self.drone

        def download_mission_assets(reasoning: str) -> str:
            """Downloads terrain map (drone.png) and converts documentation (drone.html -> drone.md) in workspace."""
            try:
                res = _run_coroutine_sync(drone.download_mission_assets(session_id=session_id, reasoning=reasoning))
                return json.dumps(res)
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Check network connection or retry."})

        def inspect_dam_coordinates(reasoning: str) -> str:
            """Vision Worker: Analyzes drone.png to extract 1-indexed dam coordinates."""
            try:
                dam_coords = _run_coroutine_sync(drone.inspect_dam_coordinates(session_id=session_id, reasoning=reasoning))
                state_tracker["dam_coordinates"] = dam_coords
                return dam_coords.model_dump_json()
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Ensure drone.png is downloaded first."})

        def list_markdown_sections(reasoning: str, file_path: str = "drone.md") -> str:
            """Lists all section headings and levels in drone.md."""
            try:
                sections = _run_coroutine_sync(drone.list_markdown_sections(session_id=session_id, file_path=file_path))
                return json.dumps({"sections": sections, "hint": "Use read_markdown_section with heading."})
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        def read_markdown_section(section_heading: str, reasoning: str, file_path: str = "drone.md") -> str:
            """Reads the content of a specific heading in drone.md."""
            try:
                return _run_coroutine_sync(drone.read_markdown_section(session_id=session_id, section_heading=section_heading, file_path=file_path))
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        def read_file_lines(start_line: int, line_count: int, reasoning: str, file_path: str = "drone.md") -> str:
            """Reads an exact line window (1-indexed) from drone.md."""
            try:
                return _run_coroutine_sync(drone.read_file_lines(session_id=session_id, start_line=start_line, line_count=line_count, file_path=file_path))
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        def grep_documentation(pattern: str, reasoning: str, file_path: str = "drone.md") -> str:
            """Searches documentation for keywords or command patterns."""
            try:
                return _run_coroutine_sync(drone.grep_documentation(session_id=session_id, pattern=pattern, file_path=file_path))
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        def verify_drone_instructions(instructions: List[str], reasoning: str) -> str:
            """Submits drone instructions to Centrala /verify and checks response."""
            state_tracker["instructions"] = instructions
            state_tracker["iterations"] += 1
            try:
                resp = _run_coroutine_sync(drone.verify_drone(session_id=session_id, instructions=instructions, reasoning=reasoning))
                if resp.flag:
                    state_tracker["flag"] = resp.flag
                return resp.model_dump_json()
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "If locked, prepend 'hardReset'."})

        return [
            download_mission_assets,
            inspect_dam_coordinates,
            list_markdown_sections,
            read_markdown_section,
            read_file_lines,
            grep_documentation,
            verify_drone_instructions,
        ]

    async def solve(self, session_id: str, max_iterations: int = 10) -> RunTaskResponse:
        logger.info(f"Starting Google ADK solve for session {session_id} using model {config.GEMINI_MODEL}")

        state_tracker: Dict[str, Any] = {
            "flag": None,
            "dam_coordinates": None,
            "instructions": [],
            "iterations": 0,
        }

        # 1. Audit Session Start
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Initialized Google ADK session {session_id} with Gemini 3.8 Flash",
            step_type="SESSION_START",
            metadata={"max_iterations": max_iterations, "model": config.GEMINI_MODEL},
        )

        tools = self._create_adk_tools(session_id=session_id, state_tracker=state_tracker)

        root_agent = Agent(
            name="drone_agent",
            model=self.prompt_config.model or config.GEMINI_MODEL,
            instruction=self.prompt_config.system_prompt,
            tools=tools,
        )

        session_service = InMemorySessionService()
        runner = Runner(
            app_name="s02e05_adk",
            agent=root_agent,
            session_service=session_service,
            auto_create_session=True,
        )

        initial_goal = (
            "Initiate preemptive strike mission for drone.\n"
            "Step 1: Download mission assets via download_mission_assets().\n"
            "Step 2: Locate dam coordinates via inspect_dam_coordinates().\n"
            "Step 3: Analyze drone.md via documentation RAG tools to determine minimal valid commands.\n"
            "Step 4: Register official mission target PWR6132PL, route physical flight to dam coordinates, and detonate payload.\n"
            "Step 5: Verify via verify_drone_instructions(). If errors occur, adapt dynamically or issue hardReset."
        )

        loop_counter = 0
        while loop_counter < max_iterations and not state_tracker["flag"]:
            loop_counter += 1
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
                logger.error(f"Error during ADK runner execution (iter {loop_counter}): {e}")
                await self.audit.log_event(
                    session_id=session_id,
                    actor="agent",
                    content=f"ADK runner error: {e}",
                    step_type="AGENT_ERROR",
                    metadata={"error": str(e), "iteration": loop_counter},
                )

            if state_tracker["flag"]:
                logger.info(f"Flag captured successfully on iteration {loop_counter}!")
                break

            initial_goal = (
                f"Iteration {loop_counter + 1}: Flag not yet captured. "
                "Review the feedback from the previous verify_drone_instructions attempt. "
                "If the API reported command syntax or sequence errors, adjust arguments based on drone.md. "
                "If state appears locked or invalid, prepend 'hardReset' as the first instruction and resubmit."
            )

        # 2. Save Execution Summary to run_notes.txt
        now_str = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        status_str = "SUCCESS" if state_tracker["flag"] else "FAILED"
        coords_str = (
            f"({state_tracker['dam_coordinates'].dam_column}, {state_tracker['dam_coordinates'].dam_row})"
            if state_tracker.get("dam_coordinates")
            else "UNKNOWN"
        )
        report_content = (
            f"Task: {config.TASK_NAME} (S02E05)\n"
            f"Backend: adk\n"
            f"Session ID: {session_id}\n"
            f"Timestamp: {now_str}\n"
            f"Status: {status_str}\n"
            f"Iterations: {state_tracker['iterations']}\n"
            f"Dam Coordinates: {coords_str}\n"
            f"Final Instructions: {state_tracker.get('instructions', [])}\n"
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
            metadata={"status": status_str, "iterations": state_tracker["iterations"], "tracker": {
                "dam_coords": coords_str,
                "instructions": state_tracker.get("instructions", []),
            }},
        )

        return RunTaskResponse(
            status="success" if state_tracker["flag"] else "failed",
            session_id=session_id,
            backend="adk",
            flag=state_tracker["flag"],
            iterations=state_tracker["iterations"],
            dam_coordinates=state_tracker.get("dam_coordinates"),
            instructions=state_tracker.get("instructions", []),
            summary=f"Mission finished with status: {status_str}.",
        )
