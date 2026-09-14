import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from af_aidevs.utils.prompts import load_system_prompt

import config
from agents.base import BaseReactorAgent
from schemas import (
    CalculateTrajectoryInput,
    ResetSimulationInput,
    RunTaskResponse,
    StartMissionInput,
    StepRobotInput,
)
from services.audit_service import AuditService, BigQueryCallbackHandler
from services.mcp_service import MCPService
from services.pathfinding_service import PathfindingService
from services.reactor_service import ReactorService
from services.safety_guardrail import SafetyGuardrailService

logger = logging.getLogger("agents.langchain")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


class LangChainReactorAgent(BaseReactorAgent):
    """LangChain 1.2.15 implementation for Autonomous Reactor Navigation using Gemini 3.8 Flash."""

    def __init__(self):
        self.prompt_config = load_system_prompt(
            base_dir=str(Path(__file__).parent.parent)
        )
        self.audit = AuditService(
            dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE
        )
        self.mcp = MCPService()
        self.reactor = ReactorService(mcp_service=self.mcp)

        os.environ["LANGSMITH_PROJECT"] = config.LANGSMITH_PROJECT

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
        reactor = self.reactor
        mcp = self.mcp

        @tool(args_schema=StartMissionInput)
        async def start_mission(reasoning: str) -> str:
            """Initiates the reactor chamber simulation session and retrieves the starting board configuration."""
            try:
                board, is_goal, is_col, flag = await reactor.send_command(
                    session_id=session_id, command="start"
                )
                if flag:
                    state_tracker["flag"] = flag
                return json.dumps(
                    {
                        "status": "started",
                        "robot_column": board.robot_column,
                        "robot_row": board.robot_row,
                        "blocks": [b.model_dump() for b in board.blocks],
                        "raw_map": board.raw_map,
                        "message": board.message,
                        "hint": "Now call calculate_safe_trajectory to plan your collision-free path.",
                    }
                )
            except Exception as e:
                logger.error(f"Error starting mission: {e}")
                return json.dumps({"status": "error", "message": str(e)})

        @tool(args_schema=CalculateTrajectoryInput)
        async def calculate_safe_trajectory(
            reasoning: str, target_column: int = 7
        ) -> str:
            """Uses the discrete Kinematic Simulator and State-Space BFS solver to find the optimal collision-free path to slot G."""
            board = reactor.last_board_state
            if not board:
                return json.dumps(
                    {
                        "error": "Mission not started. Call start_mission first to inspect the board."
                    }
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
            return json.dumps(
                {
                    "planned_commands": path,
                    "estimated_steps": len(path),
                    "reasoning": f"Calculated {len(path)}-step collision-free trajectory: {' -> '.join(path)}.",
                    "hint": f"Dispatch the first command '{path[0]}' using step_robot.",
                }
            )

        @tool(args_schema=StepRobotInput)
        async def step_robot(command: str, reasoning: str) -> str:
            """Dispatches a single discrete movement command (right, left, wait) to the robot."""
            board = reactor.last_board_state
            cur_col = board.robot_column if board else 1
            cur_blocks = {b.column: b for b in board.blocks} if board else {}

            # Pre-flight guardrail validation
            is_safe, expl, target_col = SafetyGuardrailService.validate_command(
                current_col=cur_col, command=command, current_blocks=cur_blocks
            )

            if not is_safe:
                logger.warning(f"Guardrail intercepted dangerous command '{command}': {expl}")
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

            # Send validated command via cr-mcp-web-gateway
            try:
                new_board, is_goal, is_col, flag = await reactor.send_command(
                    session_id=session_id, command=command
                )
                state_tracker["executed_commands"].append(command)
                state_tracker["steps_executed"] = len(state_tracker["executed_commands"])

                if flag:
                    state_tracker["flag"] = flag
                    logger.info(f"Course flag captured: {flag}")

                return json.dumps(
                    {
                        "command_executed": command,
                        "current_column": new_board.robot_column,
                        "is_goal_reached": is_goal,
                        "is_collision": is_col,
                        "message": new_board.message,
                        "flag": flag,
                        "raw_map": new_board.raw_map,
                        "hint": "Goal reached! Remember to write execution summary to run_notes.txt."
                        if is_goal
                        else "Continue along planned trajectory.",
                    }
                )
            except Exception as e:
                logger.error(f"Error in step_robot: {e}")
                return json.dumps(
                    {
                        "command_executed": command,
                        "current_column": cur_col,
                        "is_goal_reached": False,
                        "is_collision": False,
                        "message": str(e),
                    }
                )

        @tool(args_schema=ResetSimulationInput)
        async def reset_simulation(reasoning: str) -> str:
            """Sends an emergency reset to restore the board to the initial chamber state."""
            try:
                board, is_goal, is_col, flag = await reactor.send_command(
                    session_id=session_id, command="reset"
                )
                state_tracker["executed_commands"].clear()
                return json.dumps(
                    {
                        "status": "reset",
                        "robot_column": board.robot_column,
                        "blocks": [b.model_dump() for b in board.blocks],
                        "message": board.message,
                        "hint": "Recalculate trajectory using calculate_safe_trajectory.",
                    }
                )
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        # Workspace MCP Tools
        @tool
        async def write_file(file_path: str, content: str, reasoning: str) -> str:
            """Writes a file into the session workspace on GCS via cr-mcp-workspace (e.g. run_notes.txt)."""
            res = await mcp.write_file(
                session_id=session_id,
                file_path=file_path,
                content=content,
                reasoning=reasoning,
            )
            return json.dumps(res)

        @tool
        async def read_file(file_path: str, reasoning: str) -> str:
            """Reads a file from the session workspace via cr-mcp-workspace."""
            res = await mcp.read_file(
                session_id=session_id, file_path=file_path, reasoning=reasoning
            )
            return json.dumps(res)

        @tool
        async def list_files(reasoning: str = "List workspace files") -> str:
            """Lists files in the current session workspace via cr-mcp-workspace."""
            res = await mcp.list_files(session_id=session_id, reasoning=reasoning)
            return json.dumps(res)

        tools = [
            start_mission,
            calculate_safe_trajectory,
            step_robot,
            reset_simulation,
            write_file,
            read_file,
            list_files,
        ]

        # Graceful Tool Error Handling
        for t in tools:
            t.handle_tool_error = True

        return tools

    async def solve(
        self, session_id: str, max_iterations: int = 25
    ) -> RunTaskResponse:
        logger.info(
            f"Starting LangChain solve for session {session_id} using model {config.GEMINI_MODEL}"
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
            content=f"Initialized LangChain session {session_id} with Gemini 3.8 Flash",
            step_type="SESSION_START",
            metadata={"max_iterations": max_iterations, "model": config.GEMINI_MODEL},
        )

        tools = self._create_tools(session_id=session_id, state_tracker=state_tracker)
        bq_callback = BigQueryCallbackHandler(
            audit_service=self.audit, session_id=session_id
        )

        agent_graph = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=self.prompt_config.system_prompt,
        )

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
                f"=== Reactor Navigation Iteration {loop_counter}/{max_iterations} ==="
            )

            try:
                await agent_graph.ainvoke(
                    {"messages": [{"role": "user", "content": initial_goal}]},
                    config={"callbacks": [bq_callback]},
                )
            except Exception as e:
                logger.error(
                    f"Error during LangChain invocation (iteration {loop_counter}): {e}"
                )
                await self.audit.log_event(
                    session_id=session_id,
                    actor="agent",
                    content=f"Agent execution error: {e}",
                    step_type="AGENT_ERROR",
                    metadata={"error": str(e), "iteration": loop_counter},
                )

        # Ensure run_notes.txt is saved
        flag = state_tracker["flag"] or self.reactor.flag
        summary_content = (
            f"# S03E03 Mission Execution Report\n\n"
            f"- **Timestamp**: {datetime.now(ZURICH_TZ).isoformat()}\n"
            f"- **Session ID**: {session_id}\n"
            f"- **Backend**: langchain\n"
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
            content="Reactor mission finished",
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
            backend="langchain",
            session_id=session_id,
            steps_executed=state_tracker["steps_executed"],
            planned_commands=[str(c) for c in state_tracker["planned_commands"]],
            executed_commands=[str(c) for c in state_tracker["executed_commands"]],
            flag=flag,
            details=f"Cooling module installed at slot G with {state_tracker['steps_executed']} steps."
            if flag
            else "Navigation did not capture course flag.",
        )
