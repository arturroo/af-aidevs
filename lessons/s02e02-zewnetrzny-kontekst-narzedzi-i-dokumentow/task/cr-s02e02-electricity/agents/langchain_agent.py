import os
import json
import logging
import httpx
from pathlib import Path
from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
from langchain.agents import create_agent
from af_aidevs.clients.mcp import get_all_mcp_tools
from af_aidevs.utils.prompts import load_system_prompt
import config
from schemas import SolverResult
from services.image_service import extract_board_pinouts
from services.puzzle_service import compute_board_rotations, generate_rotation_commands
from services.audit_service import AuditService, BigQueryCallbackHandler

logger = logging.getLogger("agents.langchain")


def load_workspace_image(file_path: str, session_id: Optional[str] = None) -> bytes:
    """Loads image bytes from mounted GCS workspace (/mnt/workspaces), local disk, or Cloud Storage API."""
    mount_root = Path(os.getenv("WORKSPACE_MOUNT_ROOT") or "/mnt/workspaces")
    if mount_root.exists() and session_id:
        session_mount = mount_root / "sa-cr-s02e02-electricity" / session_id / file_path
        if session_mount.exists():
            return session_mount.read_bytes()
        shared_mount = mount_root / "shared" / "s02e02" / file_path
        if shared_mount.exists():
            return shared_mount.read_bytes()

    local_path = Path(file_path)
    if local_path.exists():
        return local_path.read_bytes()

    solved_candidate = Path(__file__).parent.parent / file_path
    if solved_candidate.exists():
        return solved_candidate.read_bytes()

    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket("af-aidevs-workspaces")

        if session_id:
            blob = bucket.blob(f"sa-cr-s02e02-electricity/{session_id}/{file_path}")
            if blob.exists():
                return blob.download_as_bytes()

        # Check shared layer
        shared_blob = bucket.blob(f"shared/s02e02/{file_path}")
        if shared_blob.exists():
            return shared_blob.download_as_bytes()

        # Check direct blob
        direct_blob = bucket.blob(file_path)
        if direct_blob.exists():
            return direct_blob.download_as_bytes()
    except Exception as e:
        logger.warning(f"Error loading {file_path} from GCS: {e}")

    # Fallback to local solved asset
    solved_local = Path(__file__).parent.parent / "solved_electricity.png"
    if solved_local.exists():
        return solved_local.read_bytes()

    raise FileNotFoundError(f"Image {file_path} could not be located in workspace or local storage.")


def create_inspect_tool(session_id: str):
    @tool
    def inspect_circuit_grid(
        reasoning: str = "Inspecting downloaded circuit board grid against solution schematic from session workspace",
        image_path: str = "electricity.png",
    ) -> str:
        """Analyzes a downloaded 3x3 electricity board image from the session workspace against solved schematic to compute required 90-degree CW tile rotations."""
        current_board_bytes = load_workspace_image(image_path, session_id=session_id)
        solved_bytes = load_workspace_image("solved_electricity.png", session_id=session_id)

        curr_pins, curr_conf = extract_board_pinouts(current_board_bytes)
        targ_pins, _ = extract_board_pinouts(solved_bytes)
        solver_data = compute_board_rotations(curr_pins, targ_pins, curr_conf)
        commands = generate_rotation_commands(solver_data.rotations)
        return json.dumps({
            "status": "board_analyzed_from_workspace",
            "image_source": image_path,
            "rotations_matrix": solver_data.rotations,
            "rotation_commands": [{"tile": cmd.tile_id, "times_to_rotate": cmd.steps_cw} for cmd in commands],
            "confidence": solver_data.confidence,
            "instruction": "Execute each command sequentially using post_web_resource. The final rotation returns {'code': 0, 'message': '{FLG:...}'}. Do not re-inspect."
        })
    return inspect_circuit_grid


class LangChainSolverAgent:
    """LangChain 1.2.15 implementation with immediate, real-time BigQuery auditing."""

    def __init__(self):
        self.prompt_config = load_system_prompt(base_dir=str(Path(__file__).parent.parent))
        self.audit = AuditService(dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE)
        os.environ["LANGSMITH_PROJECT"] = config.LANGSMITH_PROJECT

        self.llm = ChatGoogleGenerativeAI(
            model=self.prompt_config.model,
            temperature=self.prompt_config.temperature,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=self.prompt_config.location,
            vertexai=True,
        )

    async def solve(self, session_id: str) -> SolverResult:
        logger.info(f"Starting LangChain solve for session {session_id}")

        user_goal = (
            f"Objective: Solve the 3x3 electricity routing puzzle.\n"
            f"1. Call `fetch_web_resource` to download the initial puzzle board from url='{config.AIDEVS_ELECTRICITY_DATA_URL}?reset=1' to output_path='electricity.png' in your workspace.\n"
            f"2. Call tool `inspect_circuit_grid` with image_path='electricity.png' to compute all required 90-degree CW tile rotations.\n"
            f"3. For every rotation command, call `post_web_resource` to url='{config.AIDEVS_VERIFY_URL}' with payload "
            f'{{"apikey": "{config.AIDEVS_API_KEY}", "task": "electricity", "answer": {{"rotate": "AxB"}}}}.\n'
            f"4. When the server response contains the flag '{{FLG:...}}', save the result into 'run_notes.txt' using `write_file` and return the flag in your final answer."
        )

        # 1. Immediate Audit: Session Start
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Session {session_id} initialized with backend langchain",
            step_type="session_start",
            metadata={"goal": user_goal},
        )

        # Retrieve remote MCP tools dynamically
        mcp_tools = await get_all_mcp_tools(session_id=session_id)
        inspect_tool = create_inspect_tool(session_id=session_id)
        tools = list(mcp_tools) + [inspect_tool]
        for t in tools:
            t.handle_tool_error = True

        agent = create_agent(self.llm, tools=tools, system_prompt=self.prompt_config.system_prompt)
        bq_callback = BigQueryCallbackHandler(audit_service=self.audit, session_id=session_id)

        try:
            response = await agent.ainvoke(
                {"messages": [("user", user_goal)]},
                config={"callbacks": [bq_callback]},
            )
            output_text = response["messages"][-1].content if "messages" in response else str(response)
        except Exception as e:
            logger.error(f"Error during agent execution: {e}")
            await self.audit.log_event(
                session_id=session_id,
                actor="system",
                content=f"Execution error: {str(e)}",
                step_type="session_error",
                metadata={"error": str(e)},
            )
            raise

        flag: Optional[str] = None
        if "FLG:" in output_text or "{FLG:" in output_text:
            flag = output_text

        status = "success" if flag else "completed"

        # 2. Immediate Audit: Session Completion
        await self.audit.log_event(
            session_id=session_id,
            actor="agent",
            content=f"Agent completed run. Status: {status}",
            step_type="session_complete",
            metadata={"output": output_text, "flag": flag},
        )

        return SolverResult(
            status=status,
            rotations_executed=0,
            flag=flag,
            reasoning=output_text,
        )
