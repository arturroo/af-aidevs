import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from markdownify import markdownify
from google import genai
from google.genai import types

import config
from schemas import (
    DamCoordinates,
    DroneVerificationResponse,
    DroneMissionResult,
)
from services.mcp_service import MCPService
from services.audit_service import AuditService

logger = logging.getLogger("services.drone")


class DroneService:
    """Core domain service orchestrating assets, vision extraction, documentation RAG, and verification."""

    def __init__(
        self,
        mcp_service: Optional[MCPService] = None,
        audit_service: Optional[AuditService] = None,
    ):
        self.mcp = mcp_service or MCPService()
        self.audit = audit_service or AuditService()
        self._genai_client: Optional[genai.Client] = None

    @property
    def genai_client(self) -> genai.Client:
        if self._genai_client is None:
            self._genai_client = genai.Client(
                vertexai=True,
                project=config.GOOGLE_CLOUD_PROJECT,
                location=config.GOOGLE_CLOUD_LOCATION,
            )
        return self._genai_client

    async def download_mission_assets(self, session_id: str, reasoning: str) -> Dict[str, Any]:
        """Downloads the map and documentation via Gateway and converts HTML to Markdown in workspace."""
        logger.info(f"Downloading mission assets for session {session_id}...")
        await self.audit.log_event(
            session_id=session_id,
            actor="supervisor",
            content="Downloading mission assets (drone.png, drone.html -> drone.md)",
            step_type="ASSET_DOWNLOAD_START",
            metadata={"reasoning": reasoning},
        )

        # 1. Download terrain map
        map_msg = await self.mcp.fetch_web_resource(
            session_id=session_id,
            url=config.AIDEVS_DRONE_MAP_URL,
            output_path="drone.png",
        )

        # 2. Download technical manual HTML
        docs_msg = await self.mcp.fetch_web_resource(
            session_id=session_id,
            url=config.AIDEVS_DRONE_DOCS_URL,
            output_path="drone.html",
        )

        # 3. Read HTML and convert to clean Markdown
        try:
            html_content = await self.mcp.read_file(session_id, "drone.html")
            md_content = markdownify(html_content, heading_style="ATX")
            write_msg = await self.mcp.write_file(session_id, "drone.md", md_content)
        except Exception as e:
            logger.warning(f"HTML conversion error: {e}. Writing raw documentation.")
            md_content = f"# Drone Manual\n\nFailed to convert HTML: {e}"
            write_msg = await self.mcp.write_file(session_id, "drone.md", md_content)

        res = {
            "status": "success",
            "map_result": map_msg,
            "docs_result": docs_msg,
            "markdown_result": write_msg,
            "hint": "Assets ready in workspace: 'drone.png' and 'drone.md'. Proceed to inspect_dam_coordinates and list_markdown_sections.",
        }

        await self.audit.log_event(
            session_id=session_id,
            actor="supervisor",
            content="Mission assets downloaded and drone.md generated successfully",
            step_type="ASSET_DOWNLOAD_END",
            metadata=res,
        )
        return res

    async def inspect_dam_coordinates(self, session_id: str, reasoning: str) -> DamCoordinates:
        """Vision Worker: Multimodal inspection of drone.png extracting 1-indexed dam coordinates."""
        logger.info(f"Vision Worker starting dam coordinate inspection for session {session_id}...")
        await self.audit.log_event(
            session_id=session_id,
            actor="vision_worker",
            content="Initiating multimodal visual analysis of drone.png",
            step_type="VISION_INFERENCE_START",
            metadata={"reasoning": reasoning},
        )

        gcs_uri = self.mcp.get_file_uri(session_id, "drone.png")
        local_png = Path(__file__).parent.parent / "workspace_data" / "drone.png"

        vision_prompt = (
            "You are an expert satellite terrain imagery and reconnaissance analysis specialist. "
            "Analyze the provided grid map of Żarnowiec.\n\n"
            "Instructions:\n"
            "1. Count the total number of columns on the grid (from left to right, 1-indexed).\n"
            "2. Count the total number of rows on the grid (from top to bottom, 1-indexed).\n"
            "3. Locate the dam structure on or adjacent to Lake Żarnowieckie. The dam sector is distinguished by "
            "accentuated, deeper water color saturation and a weir structure separating the lake.\n"
            "4. Determine the exact 1-indexed (column, row) coordinates of the sector containing the dam.\n"
            "5. Provide your visual evidence and step-by-step reasoning."
        )

        thinking_cfg = None
        try:
            thinking_cfg = types.ThinkingConfig(thinking_level=config.THINKING_LEVEL)
        except Exception:
            try:
                thinking_cfg = types.ThinkingConfig(thinking_budget=1024)
            except Exception:
                pass

        gen_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DamCoordinates,
            thinking_config=thinking_cfg,
            temperature=0.1,
        )

        part = None
        # Try local bytes if available for local execution
        if local_png.exists():
            image_bytes = local_png.read_bytes()
            part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        else:
            # GCS URI for Cloud Run deployment
            part = types.Part.from_uri(file_uri=gcs_uri, mime_type="image/png")

        try:
            response = self.genai_client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=[part, vision_prompt],
                config=gen_config,
            )
            raw_text = response.text
            dam_coords = DamCoordinates.model_validate_json(raw_text)
        except Exception as e:
            logger.warning(f"Direct multimodal inference encountered: {e}. Attempting fallback parsing.")
            # If Part.from_uri failed on local machine, try fetching bytes via gateway
            if not local_png.exists():
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        r = await client.get(config.AIDEVS_DRONE_MAP_URL)
                        part = types.Part.from_bytes(data=r.content, mime_type="image/png")
                        response = self.genai_client.models.generate_content(
                            model=config.GEMINI_MODEL,
                            contents=[part, vision_prompt],
                            config=gen_config,
                        )
                        dam_coords = DamCoordinates.model_validate_json(response.text)
                    return dam_coords
                except Exception as inner_e:
                    raise RuntimeError(f"Vision Worker failed to extract coordinates: {inner_e}")
            raise RuntimeError(f"Vision Worker failed: {e}")

        await self.audit.log_event(
            session_id=session_id,
            actor="vision_worker",
            content=f"Vision Worker localized dam at col={dam_coords.dam_column}, row={dam_coords.dam_row}",
            step_type="VISION_INFERENCE_END",
            metadata=dam_coords.model_dump(),
        )
        return dam_coords

    async def list_markdown_sections(self, session_id: str, file_path: str = "drone.md") -> List[Dict[str, Any]]:
        """Parses and lists heading hierarchy from the documentation markdown in workspace."""
        content = await self.mcp.read_file(session_id, file_path)
        sections = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                match = re.match(r"^(#+)\s+(.+)$", stripped)
                if match:
                    level = len(match.group(1))
                    title = match.group(2).strip()
                    sections.append({"level": level, "title": title})
        return sections

    async def read_markdown_section(self, session_id: str, section_heading: str, file_path: str = "drone.md") -> str:
        """Extracts the body text belonging strictly to the specified section heading."""
        content = await self.mcp.read_file(session_id, file_path)
        lines = content.splitlines()

        target_idx = -1
        target_level = 0
        norm_target = section_heading.lower().strip()

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                match = re.match(r"^(#+)\s+(.+)$", stripped)
                if match:
                    level = len(match.group(1))
                    title = match.group(2).strip().lower()
                    if norm_target in title or title in norm_target:
                        target_idx = i
                        target_level = level
                        break

        if target_idx == -1:
            return f"Section '{section_heading}' not found in {file_path}. Use list_markdown_sections to see available titles."

        extracted = [lines[target_idx]]
        for line in lines[target_idx + 1:]:
            stripped = line.strip()
            if stripped.startswith("#"):
                match = re.match(r"^(#+)\s+(.+)$", stripped)
                if match and len(match.group(1)) <= target_level:
                    break
            extracted.append(line)

        return "\n".join(extracted)

    async def read_file_lines(self, session_id: str, start_line: int, line_count: int, file_path: str = "drone.md") -> str:
        """Reads a specific window of lines (1-indexed) from a workspace file."""
        content = await self.mcp.read_file(session_id, file_path)
        lines = content.splitlines()

        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), start_idx + line_count)

        selected = lines[start_idx:end_idx]
        annotated = [f"{start_idx + 1 + i}: {line}" for i, line in enumerate(selected)]
        return "\n".join(annotated)

    async def grep_documentation(self, session_id: str, pattern: str, file_path: str = "drone.md") -> str:
        """Searches lines matching regex or substring pattern in the documentation."""
        content = await self.mcp.read_file(session_id, file_path)
        lines = content.splitlines()

        matches = []
        reg = re.compile(pattern, re.IGNORECASE)
        for i, line in enumerate(lines):
            if reg.search(line):
                matches.append(f"{i + 1}: {line}")

        if not matches:
            return f"No matches found for pattern '{pattern}' in {file_path}."
        return "\n".join(matches)

    async def verify_drone(self, session_id: str, instructions: List[str], reasoning: str) -> DroneVerificationResponse:
        """Dispatches candidate instruction array to Centrala /verify via Gateway and parses feedback."""
        logger.info(f"Submitting {len(instructions)} drone instructions to verification hub...")
        payload = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": {
                "instructions": instructions
            }
        }

        await self.audit.log_event(
            session_id=session_id,
            actor="supervisor",
            content=f"Submitting {len(instructions)} drone instructions to {config.AIDEVS_VERIFY_URL}",
            step_type="VERIFY_ATTEMPT_START",
            metadata={"instructions": instructions, "reasoning": reasoning},
        )

        response_dict = await self.mcp.post_web_resource(
            session_id=session_id,
            url=config.AIDEVS_VERIFY_URL,
            payload=payload,
        )

        code = int(response_dict.get("code", 0) or 0)
        message = str(response_dict.get("message") or response_dict.get("raw_output") or "")

        # Extract flag if present
        flag_match = re.search(r"(\{FLG:[^}]+\})", message)
        flag = flag_match.group(1) if flag_match else None
        is_success = bool(flag) or ("OK" in message.upper() and code == 0)

        # Infer hint if failed
        hint = None
        if not is_success:
            if "reset" in message.lower() or "lock" in message.lower() or "state" in message.lower():
                hint = "Drone state may be corrupted or locked. Prepend 'hardReset' as the first instruction."
            elif "target" in message.lower():
                hint = f"Verify mission target registration matches '{config.MISSION_TARGET}'."
            elif "coordinate" in message.lower() or "bounds" in message.lower():
                hint = "Check coordinate syntax and 1-indexed bounds against DamCoordinates."

        resp = DroneVerificationResponse(
            code=code,
            message=message,
            flag=flag,
            is_success=is_success,
            hint=hint,
        )

        await self.audit.log_event(
            session_id=session_id,
            actor="supervisor",
            content=f"Verification response: code={code}, success={is_success}",
            step_type="VERIFY_ATTEMPT_END",
            metadata={"code": code, "message": message, "is_success": is_success},
            flag=flag,
        )
        return resp
