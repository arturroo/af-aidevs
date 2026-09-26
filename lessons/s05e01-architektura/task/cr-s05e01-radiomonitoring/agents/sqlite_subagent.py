import json
import logging
import sqlite3
from typing import Any

from google import genai
from google.genai import types

import config
from agents.base import DUAL_OBJECTIVE_INSTRUCTIONS, BaseSubagent
from schemas import CandidateEntities, ObjectFinding, SecretClues
from services.audit_service import AuditService
from services.mcp_service import MCPService
from services.model_armor_service import ModelArmorService

logger = logging.getLogger("agents.sqlite")

SQLITE_SUMMARY_PROMPT = f"""
You are a Database Intelligence Subagent for the Resistance.
Analyze the provided SQLite database schema and extracted table records.

{DUAL_OBJECTIVE_INSTRUCTIONS}

FORMAT INSTRUCTIONS:
Return strictly a JSON object with this exact structure:
{{
  "summary_sentences": [
    "Sentence 1: Dense factual description of the database structure and tables.",
    "Sentence 2: Findings regarding cities, safe havens, warehouses, and phone contacts.",
    "Sentence 3: Metrics, numerical values, and any telegraphist/Morse clues."
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
    "raw_clue": "exact record content containing the clue or null",
    "extracted_key": "decoded key or null"
  }},
  "confidence": 0.95,
  "reasoning": "explanation of extracted database facts"
}}
"""


class SQLiteSubagent(BaseSubagent):
    """Subagent performing deterministic schema introspection and read-only querying of SQLite files."""

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

    def introspect_and_dump(
        self, db_bytes: bytes
    ) -> tuple[dict[str, str], dict[str, list[dict[str, Any]]]]:
        """Introspects tables and reads sample rows in strict read-only in-memory mode."""
        conn = sqlite3.connect(":memory:")
        # Load database bytes into memory
        conn.deserialize(db_bytes)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. Fetch schemas
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
        schemas = {row["name"]: row["sql"] or "" for row in cursor.fetchall()}

        # 2. Fetch sample rows per table (max 50)
        table_dumps = {}
        for table_name in schemas:
            if table_name.startswith("sqlite_"):
                continue
            try:
                cursor.execute(f"SELECT * FROM `{table_name}` LIMIT 50;")
                rows = [dict(r) for r in cursor.fetchall()]
                table_dumps[table_name] = rows
            except Exception as e:
                logger.warning(f"Error querying table {table_name}: {e}")

        conn.close()
        return schemas, table_dumps

    async def analyze(
        self, session_id: str, file_path: str, mime_type: str
    ) -> ObjectFinding:
        logger.info(f"SQLiteSubagent analyzing {file_path}")

        # 1. Read binary bytes (serves directly from local /tmp cache)
        db_bytes = await self.mcp.read_binary_file(session_id, file_path)

        # 2. Introspect schema and sample rows
        try:
            schemas, table_dumps = self.introspect_and_dump(db_bytes)
        except Exception as e:
            logger.error(f"Failed to introspect SQLite database {file_path}: {e}")
            finding = ObjectFinding(
                source_file=file_path,
                mime_type=mime_type,
                summary_sentences=[
                    f"Corrupted or invalid SQLite database: {file_path}",
                    f"Error: {e}",
                ],
                schema_or_structure={},
                candidate_entities=CandidateEntities(),
                secret_clues=SecretClues(),
                confidence=0.1,
                reasoning=str(e),
            )
            await self.save_finding(session_id, finding)
            return finding

        # 3. Model Armor Gate on schemas and sample data
        schema_text = "\n".join([f"Table {k}: {v}" for k, v in schemas.items()])
        if self.model_armor:
            await self.model_armor.scan_text(
                schema_text, context=f"sqlite_schema:{file_path}"
            )

        # 4. LLM synthesis of database facts
        dump_summary = json.dumps(
            {"schemas": schemas, "sample_data": table_dumps},
            ensure_ascii=False,
            default=str,
        )[:8000]

        prompt = f"{SQLITE_SUMMARY_PROMPT}\n\n--- DATABASE INTROSPECTION DUMP ---\n{dump_summary}\n--- END DUMP ---"
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            data = json.loads(response.text or "{}")
        except Exception as e:
            logger.error(f"LLM analysis failed on database dump: {e}")
            data = {
                "summary_sentences": [
                    f"SQLite database {file_path} contains tables: {list(schemas.keys())}",
                    "Deterministic extraction completed.",
                ],
                "candidate_entities": {},
                "secret_clues": {},
                "confidence": 0.7,
                "reasoning": str(e),
            }

        finding = ObjectFinding(
            source_file=file_path,
            mime_type=mime_type,
            summary_sentences=data.get("summary_sentences", [])[:4],
            schema_or_structure={"tables": schemas},
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
            confidence=data.get("confidence", 0.95),
            reasoning=data.get("reasoning", "SQLite introspection extraction"),
        )

        await self.save_finding(session_id, finding)
        return finding
