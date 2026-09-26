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

logger = logging.getLogger("agents.audio")

AUDIO_PROMPT = f"""
You are an Acoustic & Signal Intelligence Subagent for the Resistance.
Listen carefully to the provided audio transmission.

{DUAL_OBJECTIVE_INSTRUCTIONS}

SPECIFIC AUDIO CHECKS:
1. Transcribe any speech, radio conversations, or whispered messages.
2. Listen for background telegraph keys, clicking sounds, and Morse code rhythms (dots and dashes).
   Check specifically if any Morse rhythm spells:
   F (..-.) L (.-..) A (.-) G (--.) A (.-) -> (··−·  ·−··  ·−  −−·  ·−)
3. Check for any mention of cities, coordinates, warehouse counts, or phone numbers.

FORMAT INSTRUCTIONS:
Return strictly a JSON object with this exact structure:
{{
  "summary_sentences": [
    "Sentence 1: Dense description of the acoustic signal and audio quality.",
    "Sentence 2: Spoken transcription or voice content summary.",
    "Sentence 3: Acoustic markers, rhythm detection, or Morse code findings."
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
    "raw_clue": "transcription of Morse rhythm or null",
    "extracted_key": "decoded key or null"
  }},
  "confidence": 0.95,
  "reasoning": "explanation of audio deductions"
}}
"""


class AudioSubagent(BaseSubagent):
    """Subagent analyzing intercepted audio signals for voice transcripts and telegraphist Morse code."""

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
            model_name=model_name or config.GEMINI_MODEL,
        )
        self.client = genai.Client(
            vertexai=True,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=config.GOOGLE_CLOUD_LOCATION,
        )

    async def analyze(
        self, session_id: str, file_path: str, mime_type: str
    ) -> ObjectFinding:
        logger.info(f"AudioSubagent analyzing {file_path} ({mime_type})")

        # 1. Read binary bytes from local cache
        audio_bytes = await self.mcp.read_binary_file(session_id, file_path)
        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)

        # 2. Call Gemini multimodal with audio
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[audio_part, AUDIO_PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            raw_text = response.text or "{}"
            data = json.loads(raw_text)
        except Exception as e:
            logger.error(f"Audio analysis failed for {file_path}: {e}")
            data = {
                "summary_sentences": [
                    f"Audio artifact {file_path} processing error: {e}",
                    f"MIME type: {mime_type}",
                ],
                "candidate_entities": {},
                "secret_clues": {},
                "confidence": 0.1,
                "reasoning": str(e),
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
            confidence=data.get("confidence", 0.9),
            reasoning=data.get("reasoning", "Acoustic signal analysis"),
        )

        await self.save_finding(session_id, finding)
        return finding
