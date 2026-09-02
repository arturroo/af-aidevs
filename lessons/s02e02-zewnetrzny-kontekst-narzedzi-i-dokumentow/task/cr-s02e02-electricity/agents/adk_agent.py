import os
import json
import logging
from pathlib import Path
from typing import Optional
import httpx
from google import genai
from af_aidevs.utils.prompts import load_system_prompt
import config
from schemas import SolverResult
from services.image_service import extract_board_pinouts
from services.puzzle_service import compute_board_rotations, generate_rotation_commands
from services.audit_service import AuditService

logger = logging.getLogger("agents.adk")


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

        shared_blob = bucket.blob(f"shared/s02e02/{file_path}")
        if shared_blob.exists():
            return shared_blob.download_as_bytes()

        direct_blob = bucket.blob(file_path)
        if direct_blob.exists():
            return direct_blob.download_as_bytes()
    except Exception as e:
        logger.warning(f"Error loading {file_path} from GCS: {e}")

    solved_local = Path(__file__).parent.parent / "solved_electricity.png"
    if solved_local.exists():
        return solved_local.read_bytes()

    raise FileNotFoundError(f"Image {file_path} could not be located in workspace or local storage.")


class ADKSolverAgent:
    """Google ADK implementation with autonomous tool calling and real-time BigQuery auditing."""

    def __init__(self):
        self.prompt_config = load_system_prompt(base_dir=str(Path(__file__).parent.parent))
        self.audit = AuditService(dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE)
        self.client = genai.Client(vertexai=True, project=config.GOOGLE_CLOUD_PROJECT, location=self.prompt_config.location)

    def post_web_resource(self, url: str, payload: dict) -> dict:
        """Sends a POST request to an external web service and returns JSON response."""
        with httpx.Client(timeout=30.0) as http_client:
            resp = http_client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    def inspect_circuit_grid(self, image_path: str = "electricity.png", reasoning: str = "Inspecting circuit grid from workspace") -> str:
        """Analyzes a downloaded 3x3 electricity board image from the session workspace against solved schematic to compute required 90-degree CW tile rotations."""
        current_board_bytes = load_workspace_image(image_path)
        solved_bytes = load_workspace_image("solved_electricity.png")

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
            "instruction": "Execute each command sequentially using post_web_resource. The final rotation returns {'code': 0, 'message': '{FLG:...}'}. Do not re-call inspect_circuit_grid."
        })

    async def solve(self, session_id: str) -> SolverResult:
        logger.info(f"Starting Google ADK solve for session {session_id}")

        user_goal = (
            f"Solve the electricity puzzle on the 3x3 grid.\n"
            f"1. Call `fetch_web_resource` to download the live puzzle image from '{config.AIDEVS_ELECTRICITY_DATA_URL}?reset=1' to output_path='electricity.png' in workspace.\n"
            f"2. Inspect the grid using `inspect_circuit_grid` to compute the required 90-degree CW rotations.\n"
            f"3. For every tile needing rotation, send POST requests to '{config.AIDEVS_VERIFY_URL}' using post_web_resource with payload "
            f"{{'apikey': '{config.AIDEVS_API_KEY}', 'task': 'electricity', 'answer': {{'rotate': 'AxB'}}}}.\n"
            f"4. Once you receive the {{FLG:...}} flag, save a summary to 'run_notes.txt' using `write_file` and return the flag in your final answer."
        )

        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Session {session_id} initialized with backend ADK",
            step_type="session_start",
            metadata={"goal": user_goal},
        )

        tools = [
            self.post_web_resource,
            self.inspect_circuit_grid,
        ]

        chat = self.client.chats.create(
            model=self.prompt_config.model,
            config={
                "system_instruction": self.prompt_config.system_prompt,
                "temperature": self.prompt_config.temperature,
                "tools": tools,
            },
        )

        response = chat.send_message(user_goal)
        output_text = response.text or ""

        flag: Optional[str] = None
        if "FLG:" in output_text or "{FLG:" in output_text:
            flag = output_text

        status = "success" if flag else "completed"

        await self.audit.log_event(
            session_id=session_id,
            actor="agent",
            content=f"ADK Agent completed run. Status: {status}",
            step_type="session_complete",
            metadata={"output": output_text, "flag": flag},
        )

        return SolverResult(
            status=status,
            rotations_executed=0,
            flag=flag,
            reasoning=output_text,
        )
