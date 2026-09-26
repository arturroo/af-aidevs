import json
import logging

from google import genai
from google.genai import types

import config
from agents.base import DUAL_OBJECTIVE_INSTRUCTIONS, BaseSubagent
from schemas import CandidateEntities, ObjectFinding, SecretClues
from services.audit_service import AuditService
from services.mcp_service import MCPService
from services.model_armor_service import ModelArmorService

logger = logging.getLogger("agents.vision")

VISION_PROMPT = f"""
You are a specialized Multimodal Vision Intelligence Subagent for the Resistance.
Your task is to analyze the provided image artifact with high scrutiny.

{DUAL_OBJECTIVE_INSTRUCTIONS}

FORMAT INSTRUCTIONS:
Return strictly a JSON object with this exact structure:
{{
  "summary_sentences": [
    "Sentence 1: Dense visual classification of the image (map, diagram, photo, aerial shot, table).",
    "Sentence 2: All OCR text, markings, phone numbers, and warehouse indicators identified.",
    "Sentence 3: Geometric, spatial, or mathematical measurements (area, scale) and any Morse code / telegraph symbols."
  ],
  "candidate_entities": {{
    "city_names": ["candidate_city_1", ...],
    "city_area": "12.34 (or null if not found)",
    "warehouses_count": 12 (or null if not found),
    "phone_numbers": ["555-0192", ...]
  }},
  "secret_clues": {{
    "telegraphist_mentions": true/false,
    "morse_detected": true/false,
    "raw_clue": "exact text or symbols seen or null",
    "extracted_key": "decoded key or null"
  }},
  "confidence": 0.95,
  "reasoning": "brief explanation of visual deductions"
}}
"""


class VisionSubagent(BaseSubagent):
    """Subagent utilizing Gemini 3.5 Flash Lite with Medium Thinking for visual scene understanding and OCR."""

    def __init__(
        self,
        mcp_service: MCPService,
        audit_service: AuditService | None = None,
        model_armor_service: ModelArmorService | None = None,
        model_name: str | None = None,
    ):
        super().__init__(
            mcp_service=mcp_service,
            audit_service=audit_service,
            model_armor_service=model_armor_service,
            model_name=model_name or config.ENRICHMENT_MODEL,
        )
        self.client = genai.Client(
            vertexai=True,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=config.GOOGLE_CLOUD_LOCATION,
        )

    async def analyze(
        self, session_id: str, file_path: str, mime_type: str
    ) -> ObjectFinding:
        logger.info(f"VisionSubagent analyzing {file_path} ({mime_type})")

        # 1. Read binary bytes (serves directly from local /tmp cache in <1 ms)
        image_bytes = await self.mcp.read_binary_file(session_id, file_path)
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        # 2. Call Gemini multimodal with thinking_level="medium"
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[image_part, VISION_PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                    thinking_config=types.ThinkingConfig(thinking_level="medium"),
                ),
            )
            raw_text = response.text or "{}"
            data = json.loads(raw_text)
        except Exception as e:
            logger.error(f"Vision analysis failed for {file_path}: {e}")
            data = {
                "summary_sentences": [
                    f"Visual artifact {file_path} analysis encountered an error.",
                    f"MIME type: {mime_type}.",
                    "Manual verification recommended.",
                ],
                "candidate_entities": {},
                "secret_clues": {},
                "confidence": 0.1,
                "reasoning": f"Exception: {e}",
            }

        finding = ObjectFinding(
            source_file=file_path,
            mime_type=mime_type,
            summary_sentences=data.get("summary_sentences", [])[:4],
            schema_or_structure={},
            candidate_entities=CandidateEntities(
                city_names=data.get("candidate_entities", {}).get("city_names", []),
                city_area=data.get("candidate_entities", {}).get("city_area"),
                warehouses_count=data.get("candidate_entities", {}).get(
                    "warehouses_count"
                ),
                phone_numbers=data.get("candidate_entities", {}).get(
                    "phone_numbers", []
                ),
            ),
            secret_clues=SecretClues(
                telegraphist_mentions=data.get("secret_clues", {}).get(
                    "telegraphist_mentions", False
                ),
                morse_detected=data.get("secret_clues", {}).get(
                    "morse_detected", False
                ),
                raw_clue=data.get("secret_clues", {}).get("raw_clue"),
                extracted_key=data.get("secret_clues", {}).get("extracted_key"),
            ),
            confidence=data.get("confidence", 0.8),
            reasoning=data.get("reasoning", "Automated vision extraction"),
        )

        await self.save_finding(session_id, finding)
        return finding
