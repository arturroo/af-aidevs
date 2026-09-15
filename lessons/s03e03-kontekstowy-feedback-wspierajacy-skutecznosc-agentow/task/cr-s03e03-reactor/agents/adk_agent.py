import asyncio
import concurrent.futures
from datetime import datetime
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
from agents.base import BaseReactorAgent
from schemas import RunTaskResponse
from services.audit_service import AuditService
from services.mcp_service import MCPService
from services.pathfinding_service import PathfindingService
from services.reactor_service import ReactorService
from services.safety_guardrail import SafetyGuardrailService

logger = logging.getLogger("agents.adk")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


def _run_coroutine_sync(coro):
    """Safely executes an async coroutine from synchronous tool functions in any event loop context."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()


class ADKReactorAgent(BaseReactorAgent):
    """Google ADK implementation (google-adk==1.33.0) with Gemini 3.8 Flash and BigQuery telemetry."""

    def __init__(self):
        self.prompt_config = load_system_prompt(
            base_dir=str(Path(__file__).parent.parent)
        )
        self.audit = AuditService(
            dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE
        )
        self.mcp = MCPService()
        self.reactor = ReactorService(mcp_service=self.mcp)

    def _create_tools(self, session_id: str, state_tracker: Dict[str, Any]):
        reactor = self.reactor
        mcp = self.mcp
        audit = self.audit

        def start_mission(reasoning: str) -> str:
            """Initiates the reactor chamber simulation session and retrieves the starting board configuration."""
            try:
                board, is_goal, is_col, flag = _run_coroutine_sync(
                    reactor.send_command(session_id=session_id, command="start")
                )
                if flag:
                    state_tracker["flag"] = flag
                _run_coroutine_sync(
                    audit.log_event(
                        session_id=session_id,
                        actor="tool",
                        content="Initiated reactor simulation via start_mission",
                        step_type="tool_call",
                        metadata={"robot_column": board.robot_column},
                    )
                )
                return json.dumps(
                    {
                        "status": "started",
                        "robot_column": board.robot_column,
                        "robot_row": board.robot_row,
                        "blocks": [b.model_dump() for b in board.blocks],
                        "raw_map": board.raw_map,
                        "message": board.message,
                        "hint": "Call calculate_safe_trajectory next.",
                    }
                )
            except Exception as e:
                logger.error(f"Error in ADK start_mission: {e}")
                return json.dumps({"status": "error", "message": str(e)})

        def calculate_safe_trajectory(reasoning: str, target_column: int = 7) -> str:
            """Uses the discrete Kinematic Simulator and State-Space BFS solver to find the optimal collision-free path to slot G."""
            board = reactor.last_board_state
            if not board:
                return json.dumps(
                    {"error": "Mission not started. Call start_mission first."}
                )

            current_blocks = {b.column: b for b in board.blocks}
            path = PathfindingService.find_shortest_safe_path(
                start_col=board.robot_column,
                target_col=target_column,
                current_blocks=current_blocks,
            )

            if path is None:
                return json.dumps(
                    {
                        "planned_commands": [],
                        "estimated_steps": 0,
                        "reasoning": f"No safe path found within lookahead horizon from col={board.robot_column}.",
                        "hint": "Try calling reset_simulation or waiting 1 turn.",
                    }
                )

            state_tracker["planned_commands"] = path
            _run_coroutine_sync(
                audit.log_event(
                    session_id=session_id,
                    actor="tool",
                    content=f"ADK Pathfinding solved trajectory: {path}",
                    step_type="tool_call",
                    metadata={"path": path},
                )
            )
            return json.dumps(
                {
                    "planned_commands": path,
                    "estimated_steps": len(path),
                    "reasoning": f"Calculated {len(path)}-step trajectory: {' -> '.join(path)}.",
                    "hint": f"Dispatch the first command '{path[0]}' using step_robot.",
                }
            )

        def step_robot(command: str, reasoning: str) -> str:
            """Dispatches a single discrete movement command (right, left, wait) to the robot."""
            board = reactor.last_board_state
            cur_col = board.robot_column if board else 1
            cur_blocks = {b.column: b for b in board.blocks} if board else {}

            # Pre-flight guardrail validation
            is_safe, expl, target_col = SafetyGuardrailService.validate_command(
                current_col=cur_col, command=command, current_blocks=cur_blocks
            )

            if not is_safe:
                logger.warning(
                    f"ADK Guardrail intercepted dangerous command '{command}': {expl}"
                )
                return json.dumps(
                    {
                        "command_executed": command,
                        "current_column": cur_col,
                        "is_goal_reached": False,
                        "is_collision": False,
                        "message": f"[SAFETY GUARDRAIL REJECTION] {expl}",
                        "hint": "Choose an alternative safe action such as 'wait' or 'left'.",
                    }
                )

            try:
                new_board, is_goal, is_col, flag = _run_coroutine_sync(
                    reactor.send_command(session_id=session_id, command=command)
                )
                state_tracker["executed_commands"].append(command)
                state_tracker["steps_executed"] = len(state_tracker["executed_commands"])

                if flag:
                    state_tracker["flag"] = flag
                    logger.info(f"ADK captured course flag: {flag}")

                _run_coroutine_sync(
                    audit.log_event(
                        session_id=session_id,
                        actor="tool",
                        content=f"Executed command: {command} -> Col {new_board.robot_column}",
                        step_type="tool_call",
                        metadata={"command": command, "is_goal": is_goal, "flag": flag},
                    )
                )

                return json.dumps(
                    {
                        "command_executed": command,
                        "current_column": new_board.robot_column,
                        "is_goal_reached": is_goal,
                        "is_collision": is_col,
                        "message": new_board.message,
                        "flag": flag,
                        "raw_map": new_board.raw_map,
                    }
                )
            except Exception as e:
                logger.error(f"Error in ADK step_robot: {e}")
                return json.dumps(
                    {
                        "command_executed": command,
                        "current_column": cur_col,
                        "is_goal_reached": False,
                        "is_collision": False,
                        "message": str(e),
                    }
                )

        def reset_simulation(reasoning: str) -> str:
            """Sends an emergency reset to restore the board to the initial chamber state."""
            try:
                board, is_goal, is_col, flag = _run_coroutine_sync(
                    reactor.send_command(session_id=session_id, command="reset")
                )
                state_tracker["executed_commands"].clear()
                return json.dumps(
                    {
                        "status": "reset",
                        "robot_column": board.robot_column,
                        "blocks": [b.model_dump() for b in board.blocks],
                        "message": board.message,
                    }
                )
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        def write_file(file_path: str, content: str, reasoning: str) -> str:
            """Writes a file into the session workspace on GCS via cr-mcp-workspace (e.g. run_notes.txt)."""
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
            """Reads a file from the session workspace via cr-mcp-workspace."""
            res = _run_coroutine_sync(
                mcp.read_file(
                    session_id=session_id, file_path=file_path, reasoning=reasoning
                )
            )
            return json.dumps(res)

        def list_files(reasoning: str = "List workspace files") -> str:
            """Lists files in the current session workspace via cr-mcp-workspace."""
            res = _run_coroutine_sync(
                mcp.list_files(session_id=session_id, reasoning=reasoning)
            )
            return json.dumps(res)

        return [
            start_mission,
            calculate_safe_trajectory,
            step_robot,
            reset_simulation,
            write_file,
            read_file,
            list_files,
        ]

    async def solve(
        self, session_id: str, max_iterations: int = 25
    ) -> RunTaskResponse:
        logger.info(
            f"Starting Google ADK solve for session {session_id} using model {config.GEMINI_MODEL}"
        )

        state_tracker: Dict[str, Any] = {
            "flag": None,
            "planned_commands": [],
            "executed_commands": [],
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

        agent = Agent(
            name="reactor_navigator",
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
            session_id=session_id, app_name="reactor_nav", user_id="artur"
        )
        runner = Runner(agent=agent, session_service=session_service, app_name="reactor_nav")

        initial_goal = (
            "Navigate the transport robot to reactor mounting slot G (Column 7, Row 5).\n"
            "Step 1: Call start_mission to retrieve initial chamber map and block telemetry.\n"
            "Step 2: Call calculate_safe_trajectory to obtain the mathematical collision-free path.\n"
            "Step 3: Execute the planned commands sequentially using step_robot.\n"
            "Step 4: When slot G is reached and the course flag {FLG:...} is acquired, call write_file to save run_notes.txt."
        )

        loop_counter = 0
        while loop_counter < max_iterations and not state_tracker["flag"]:
            loop_counter += 1
            logger.info(
                f"=== ADK Reactor Navigation Iteration {loop_counter}/{max_iterations} ==="
            )

            try:
                user_msg = types.Content(
                    role="user", parts=[types.Part.from_text(text=initial_goal)]
                )
                events = runner.run(
                    session_id=session_id, user_id="artur", message=user_msg
                )
                for event in events:
                    if hasattr(event, "content") and event.content:
                        for part in event.content.parts:
                            if hasattr(part, "text") and part.text:
                                await self.audit.log_event(
                                    session_id=session_id,
                                    actor="adk_agent",
                                    content=part.text[:500],
                                    step_type="thought",
                                )
            except Exception as e:
                logger.error(f"Error during ADK runner execution: {e}")
                await self.audit.log_event(
                    session_id=session_id,
                    actor="adk_agent",
                    content=f"ADK runner error: {e}",
                    step_type="AGENT_ERROR",
                    metadata={"error": str(e)},
                )

        # Ensure run_notes.txt is saved
        flag = state_tracker["flag"] or self.reactor.flag
        summary_content = (
            f"# S03E03 Mission Execution Report (ADK)\n\n"
            f"- **Timestamp**: {datetime.now(ZURICH_TZ).isoformat()}\n"
            f"- **Session ID**: {session_id}\n"
            f"- **Backend**: adk\n"
            f"- **Status**: {'SUCCESS' if flag else 'INCOMPLETE'}\n"
            f"- **Steps Executed**: {state_tracker['steps_executed']}\n"
            f"- **Planned Sequence**: {state_tracker['planned_commands']}\n"
            f"- **Executed Sequence**: {state_tracker['executed_commands']}\n"
            f"- **Flag**: {flag or 'NONE'}\n"
        )
        try:
            await self.mcp.write_file(
                session_id=session_id,
                file_path="run_notes.txt",
                content=summary_content,
                reasoning="Persist post-mission summary to workspace",
            )
        except Exception as e:
            logger.warning(f"Could not persist run_notes.txt: {e}")

        # Final BigQuery Audit Log
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content="Reactor mission finished (ADK)",
            step_type="TASK_COMPLETE" if flag else "TASK_FAILED",
            flag=flag,
            metadata={
                "steps_executed": state_tracker["steps_executed"],
                "executed_commands": state_tracker["executed_commands"],
                "planned_commands": state_tracker["planned_commands"],
            },
        )

        return RunTaskResponse(
            status="success" if flag else "failure",
            backend="adk",
            session_id=session_id,
            steps_executed=state_tracker["steps_executed"],
            planned_commands=[str(c) for c in state_tracker["planned_commands"]],
            executed_commands=[str(c) for c in state_tracker["executed_commands"]],
            flag=flag,
            details=f"Cooling module installed at slot G with {state_tracker['steps_executed']} steps."
            if flag
            else "Navigation did not capture course flag.",
        )
