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
    DownloadMissionAssetsRequest,
    InspectDamCoordinatesRequest,
    ListMarkdownSectionsRequest,
    ReadMarkdownSectionRequest,
    ReadFileLinesRequest,
    GrepDocumentationRequest,
    VerifyInstructionsRequest,
    DamCoordinates,
)
from services.audit_service import AuditService, BigQueryCallbackHandler
from services.mcp_service import MCPService
from services.drone_service import DroneService
from agents.base import BaseDroneAgent

logger = logging.getLogger("agents.langchain")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


class LangChainDroneAgent(BaseDroneAgent):
    """LangChain 1.2.15 agent implementation on Vertex AI with Gemini 3.8 Flash."""

    def __init__(self):
        self.prompt_config = load_system_prompt(base_dir=str(Path(__file__).parent.parent))
        self.audit = AuditService(dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE)
        self.mcp = MCPService()
        self.drone = DroneService(mcp_service=self.mcp, audit_service=self.audit)

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
        drone = self.drone

        @tool(args_schema=DownloadMissionAssetsRequest)
        async def download_mission_assets(reasoning: str) -> str:
            """Downloads terrain map (drone.png) and documentation (drone.html -> drone.md) into the workspace."""
            try:
                res = await drone.download_mission_assets(session_id=session_id, reasoning=reasoning)
                return json.dumps(res)
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Check network connectivity or retry download."})

        @tool(args_schema=InspectDamCoordinatesRequest)
        async def inspect_dam_coordinates(reasoning: str) -> str:
            """Vision Worker: Analyzes drone.png to extract 1-indexed dam sector coordinates (col, row)."""
            try:
                dam_coords = await drone.inspect_dam_coordinates(session_id=session_id, reasoning=reasoning)
                state_tracker["dam_coordinates"] = dam_coords
                return dam_coords.model_dump_json()
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Ensure drone.png is downloaded first."})

        @tool(args_schema=ListMarkdownSectionsRequest)
        async def list_markdown_sections(reasoning: str, file_path: str = "drone.md") -> str:
            """Lists all section headings and levels in the converted markdown manual."""
            try:
                sections = await drone.list_markdown_sections(session_id=session_id, file_path=file_path)
                return json.dumps({"sections": sections, "hint": "Use read_markdown_section with a heading title."})
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Ensure drone.md is present."})

        @tool(args_schema=ReadMarkdownSectionRequest)
        async def read_markdown_section(section_heading: str, reasoning: str, file_path: str = "drone.md") -> str:
            """Reads the complete content of a specific heading in the documentation."""
            try:
                content = await drone.read_markdown_section(
                    session_id=session_id,
                    section_heading=section_heading,
                    file_path=file_path,
                )
                return content
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Verify section title exists."})

        @tool(args_schema=ReadFileLinesRequest)
        async def read_file_lines(start_line: int, line_count: int, reasoning: str, file_path: str = "drone.md") -> str:
            """Reads an exact line window (1-indexed) from the documentation for syntax verification."""
            try:
                lines_text = await drone.read_file_lines(
                    session_id=session_id,
                    start_line=start_line,
                    line_count=line_count,
                    file_path=file_path,
                )
                return lines_text
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Check line range bounds."})

        @tool(args_schema=GrepDocumentationRequest)
        async def grep_documentation(pattern: str, reasoning: str, file_path: str = "drone.md") -> str:
            """Searches documentation for keywords or command patterns."""
            try:
                matches = await drone.grep_documentation(
                    session_id=session_id,
                    pattern=pattern,
                    file_path=file_path,
                )
                return matches
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "Adjust pattern regex."})

        @tool(args_schema=VerifyInstructionsRequest)
        async def verify_drone_instructions(instructions: List[str], reasoning: str) -> str:
            """Submits ordered drone instructions to Centrala /verify endpoint and checks for flag."""
            state_tracker["instructions"] = instructions
            state_tracker["iterations"] += 1
            try:
                resp = await drone.verify_drone(
                    session_id=session_id,
                    instructions=instructions,
                    reasoning=reasoning,
                )
                if resp.flag:
                    state_tracker["flag"] = resp.flag
                return resp.model_dump_json()
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "hint": "If drone is locked, consider prepending 'hardReset'."})

        tools = [
            download_mission_assets,
            inspect_dam_coordinates,
            list_markdown_sections,
            read_markdown_section,
            read_file_lines,
            grep_documentation,
            verify_drone_instructions,
        ]

        # Graceful Tool Error Handling: convert runtime errors into ToolMessages
        for t in tools:
            t.handle_tool_error = True

        return tools

    async def solve(self, session_id: str, max_iterations: int = 10) -> RunTaskResponse:
        logger.info(f"Starting LangChain solve for session {session_id} using model {config.GEMINI_MODEL}")

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
            content=f"Initialized LangChain session {session_id} with Gemini 3.8 Flash",
            step_type="SESSION_START",
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
            "Initiate preemptive strike mission for drone.\n"
            "Step 1: Download mission assets via download_mission_assets().\n"
            "Step 2: Locate dam coordinates via inspect_dam_coordinates().\n"
            "Step 3: Analyze drone.md via documentation RAG tools to determine minimal valid commands.\n"
            "Step 4: Register official mission target PWR6132PL, route physical flight to dam coordinates, and detonate payload.\n"
            "Step 5: Verify via verify_drone_instructions(). If errors occur, adapt dynamically or issue hardReset."
        )

        # 3. Execution Loop with Dynamic Recovery
        loop_counter = 0
        while loop_counter < max_iterations and not state_tracker["flag"]:
            loop_counter += 1
            logger.info(f"=== Drone Mission Iteration {loop_counter}/{max_iterations} ===")

            try:
                await agent_graph.ainvoke(
                    {"messages": [{"role": "user", "content": user_goal}]},
                    config={"callbacks": [bq_callback]},
                )
            except Exception as e:
                logger.error(f"Error during agent invocation (iter {loop_counter}): {e}")
                await self.audit.log_event(
                    session_id=session_id,
                    actor="agent",
                    content=f"Agent graph execution error: {e}",
                    step_type="AGENT_ERROR",
                    metadata={"error": str(e), "iteration": loop_counter},
                )

            if state_tracker["flag"]:
                logger.info(f"Flag captured successfully on iteration {loop_counter}!")
                break

            user_goal = (
                f"Iteration {loop_counter + 1}: Flag not yet captured. "
                "Review the feedback from the previous verify_drone_instructions attempt. "
                "If the API reported command syntax or sequence errors, adjust arguments based on drone.md. "
                "If state appears locked or invalid, prepend 'hardReset' as the first instruction and resubmit."
            )

        # 4. Save Execution Summary to run_notes.txt
        now_str = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        status_str = "SUCCESS" if state_tracker["flag"] else "FAILED"
        coords_str = (
            f"({state_tracker['dam_coordinates'].dam_column}, {state_tracker['dam_coordinates'].dam_row})"
            if state_tracker.get("dam_coordinates")
            else "UNKNOWN"
        )
        report_content = (
            f"Task: {config.TASK_NAME} (S02E05)\n"
            f"Backend: langchain\n"
            f"Session ID: {session_id}\n"
            f"Timestamp: {now_str}\n"
            f"Status: {status_str}\n"
            f"Iterations: {state_tracker['iterations']}\n"
            f"Dam Coordinates: {coords_str}\n"
            f"Final Instructions: {state_tracker.get('instructions', [])}\n"
            f"Flag: {state_tracker.get('flag') or 'NOT_CAPTURED'}\n"
        )
        await self.mcp.write_file(session_id=session_id, file_path="run_notes.txt", content=report_content)

        # 5. Final Audit Log
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
            backend="langchain",
            flag=state_tracker["flag"],
            iterations=state_tracker["iterations"],
            dam_coordinates=state_tracker.get("dam_coordinates"),
            instructions=state_tracker.get("instructions", []),
            summary=f"Mission finished with status: {status_str}.",
        )
