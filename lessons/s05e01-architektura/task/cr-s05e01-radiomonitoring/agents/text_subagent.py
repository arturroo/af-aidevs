import json
import logging
from typing import Any

from google import genai
from google.genai import types

import config
from agents.base import DUAL_OBJECTIVE_INSTRUCTIONS, BaseSubagent
from schemas import CandidateEntities, ObjectFinding, SecretClues
from services.audit_service import AuditService
from services.mcp_service import MCPService
from services.model_armor_service import ModelArmorService

logger = logging.getLogger("agents.text")

TEXT_PROMPT = f"""
You are a Text & Document Intelligence Subagent for the Resistance.
Analyze the provided text document or transcript with extreme precision.

{DUAL_OBJECTIVE_INSTRUCTIONS}

FORMAT INSTRUCTIONS:
Return strictly a JSON object with this exact structure:
{{
  "summary_sentences": [
    "Sentence 1: Dense factual summary of the communication or document.",
    "Sentence 2: Mention of any settlements, resistance safe havens, and infrastructure details.",
    "Sentence 3: Specific numerical figures, contact numbers, or telegraphist/Morse references."
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
    "raw_clue": "exact text containing the clue or null",
    "extracted_key": "decoded key or null"
  }},
  "confidence": 0.95,
  "reasoning": "explanation of extracted textual evidence"
}}
"""


class TextSubagent(BaseSubagent):
    """Subagent analyzing transcripts, Markdown documents, and structured text payloads."""

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

    def extract_markdown_structure(self, text: str) -> dict[str, Any]:
        """Extracts table of contents, sections, and headers from Markdown."""
        sections = []
        for line in text.splitlines():
            line_str = line.strip()
            if line_str.startswith("#"):
                sections.append(line_str)
        return {"sections": sections}

    async def analyze(
        self, session_id: str, file_path: str, mime_type: str
    ) -> ObjectFinding:
        logger.info(f"TextSubagent analyzing {file_path} ({mime_type})")

        # 1. Read text from MCP (serves from /tmp cache)
        text_content = await self.mcp.read_file(session_id, file_path)

        # 2. Model Armor inspection gate (Silver -> Gold boundary)
        armor_flag = False
        if self.model_armor:
            armor_res = await self.model_armor.scan_text(
                text_content, context=f"file:{file_path}"
            )
            if not armor_res.get("is_safe", True):
                armor_flag = True
                logger.warning(
                    f"Model Armor flagged potential injection in {file_path}: {armor_res.get('threats')}"
                )

        # 3. Structural extraction for Markdown
        structure = {}
        if mime_type == "text/markdown" or file_path.endswith(".md"):
            structure = self.extract_markdown_structure(text_content)

        # 4. LLM Analysis
        prompt_with_doc = f"{TEXT_PROMPT}\n\n--- DOCUMENT CONTENT ({file_path}) ---\n{text_content[:8000]}\n--- END DOCUMENT ---"
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt_with_doc],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            raw_text = response.text or "{}"
            data = json.loads(raw_text)
        except Exception as e:
            logger.error(f"Text analysis failed for {file_path}: {e}")
            data = {
                "summary_sentences": [
                    f"Text artifact {file_path} processing error: {e}",
                    f"Content preview: {text_content[:100]}",
                ],
                "candidate_entities": {},
                "secret_clues": {},
                "confidence": 0.2,
                "reasoning": str(e),
            }

        finding = ObjectFinding(
            source_file=file_path,
            mime_type=mime_type,
            summary_sentences=data.get("summary_sentences", [])[:4],
            schema_or_structure=structure,
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
            confidence=0.5 if armor_flag else data.get("confidence", 0.9),
            reasoning=f"ModelArmorFlag={armor_flag}. " + data.get("reasoning", ""),
        )

        await self.save_finding(session_id, finding)
        return finding
