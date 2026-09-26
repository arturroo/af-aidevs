import json
import logging
import re
from decimal import ROUND_HALF_UP, Decimal

from google import genai
from google.genai import types

import config
from schemas import ObjectFinding, RunTaskResponse
from services.audit_service import AuditService
from services.centrala_service import CentralaService
from services.mcp_service import MCPService

logger = logging.getLogger("agents.synthesis")


def format_city_area(raw_value: float | str | Decimal) -> str:
    """Deterministic mathematical rounding to exactly two decimal places using ROUND_HALF_UP."""
    raw_str = (
        str(raw_value)
        .strip()
        .replace(",", ".")
        .replace("km²", "")
        .replace("km2", "")
        .strip()
    )
    match = re.search(r"(\d+(\.\d+)?)", raw_str)
    if not match:
        raise ValueError(f"Unable to parse numeric value from area string: {raw_value}")
    clean_num = match.group(1)
    d = Decimal(clean_num)
    rounded = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:.2f}"


SYNTHESIS_SYSTEM_PROMPT = """
You are the Commander Synthesis Agent for the Resistance Operation.
You have received a comprehensive briefing compiled from all intercepted radio communications, documents, images, audio, and database findings.

MISSION OBJECTIVES:
1. Identify the 4 critical parameters for the hidden haven known colloquially as "Syjon":
   - cityName: The true, official administrative name of the city (e.g. Skarszewy, Domatowo, etc.).
   - cityArea: The numeric area value of the city before rounding (e.g. 10.7284).
   - warehousesCount: The exact integer count of warehouses currently operational in Syjon.
     CRITICAL LOGIC NOTE: If a radio broadcast mentions that after a successful harvest warehouses are full and they plan to construct their 12th warehouse in spring, that means there are currently 11 operational warehouses. If the broadcast states they have 12 warehouses, output 12. Evaluate the evidence carefully.
   - phoneNumber: The phone number of the liaison or outpost commander in Syjon (e.g. from notes or trade dispatches).
2. Search for any hidden secrets or flags related to Julian Tuwim's "Piosenka telegrafisty" or the Morse sequence for FLAGA (··−· ·−·· ·− −−· ·−).

FORMAT INSTRUCTIONS:
Return strictly a JSON object:
{
  "cityName": "Official Name of the City",
  "cityAreaRaw": "10.7284",
  "warehousesCount": 11,
  "phoneNumber": "644-122-092",
  "secretFlag": "{FLG:...} or null",
  "reasoning": "Step by step deduction confirming why this city is Syjon, resolving candidates, and justifying the warehouse count."
}
"""


class SynthesisSubagent:
    """Fan-In aggregator consolidating all object findings into verified parameters for Centrala."""

    def __init__(
        self,
        mcp_service: MCPService,
        centrala_service: CentralaService,
        audit_service: AuditService | None = None,
        model_name: str | None = None,
        thinking_level: str | None = None,
    ):
        self.mcp = mcp_service
        self.centrala = centrala_service
        self.audit = audit_service
        self.model_name = model_name or config.GEMINI_MODEL
        self.thinking_level = thinking_level or config.THINKING_LEVEL
        self.client = genai.Client(
            vertexai=True,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=config.GOOGLE_CLOUD_LOCATION,
        )

    async def aggregate_findings(self, session_id: str) -> list[ObjectFinding]:
        """Loads and parses all /findings/**/*.json from workspace."""
        files = await self.mcp.list_files(session_id, directory="/findings")
        findings: list[ObjectFinding] = []

        for fpath in files:
            clean_p = fpath.lstrip("/").replace("\\", "/")
            if not clean_p.endswith(".json"):
                continue
            try:
                content = await self.mcp.read_file(session_id, clean_p)
                finding_dict = json.loads(content)
                finding = ObjectFinding.model_validate(finding_dict)
                findings.append(finding)
            except Exception as e:
                logger.warning(f"Failed to parse finding {clean_p}: {e}")

        return findings

    async def synthesize_and_transmit(
        self, session_id: str, findings: list[ObjectFinding]
    ) -> RunTaskResponse:
        """Performs final synthesis reasoning, applies deterministic rounding, and submits to Centrala."""
        logger.info(f"Synthesizing {len(findings)} findings for session {session_id}")

        # Compile concise digest of findings
        findings_digest = []
        secret_clues_found = []

        for f in findings:
            item = {
                "source": f.source_file,
                "mime": f.mime_type,
                "summary": f.summary_sentences,
                "entities": f.candidate_entities.model_dump(exclude_none=True),
            }
            if f.schema_or_structure:
                item["schema"] = f.schema_or_structure
            if (
                f.secret_clues.telegraphist_mentions
                or f.secret_clues.morse_detected
                or f.secret_clues.raw_clue
                or f.secret_clues.extracted_key
            ):
                item["secret_clues"] = f.secret_clues.model_dump(exclude_none=True)
                secret_clues_found.append(f.secret_clues)
            findings_digest.append(item)

        digest_json = json.dumps(findings_digest, indent=2, ensure_ascii=False)
        prompt = f"{SYNTHESIS_SYSTEM_PROMPT}\n\n--- AGGREGATED FINDINGS DIGEST ---\n{digest_json[:12000]}\n--- END DIGEST ---"

        # Call Gemini 3.8 Flash for synthesis
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                    thinking_config=types.ThinkingConfig(
                        thinking_level=self.thinking_level
                    ),
                ),
            )
            raw_text = response.text or "{}"
            result_data = json.loads(raw_text)
        except Exception as e:
            logger.error(f"Synthesis reasoning failed: {e}")
            return RunTaskResponse(
                status="error",
                session_id=session_id,
                error=f"Synthesis reasoning failed: {e}",
            )

        city_name = result_data.get("cityName", "").strip()
        raw_area = result_data.get("cityAreaRaw") or result_data.get("cityArea", "0.0")
        warehouses_count = int(result_data.get("warehousesCount", 0))
        phone_number = str(result_data.get("phoneNumber", "")).strip()
        secret_flag = result_data.get("secretFlag")

        # Deterministic mathematical rounding
        try:
            formatted_area = format_city_area(raw_area)
        except Exception as e:
            logger.error(f"Rounding failed for raw area '{raw_area}': {e}")
            formatted_area = "0.00"

        # Transmit to Centrala
        try:
            transmit_result = await self.centrala.transmit(
                session_id=session_id,
                city_name=city_name,
                city_area=formatted_area,
                warehouses_count=warehouses_count,
                phone_number=phone_number,
            )
            mission_flag = transmit_result.get("flag") or (
                transmit_result.get("message")
                if "{FLG:" in str(transmit_result.get("message"))
                else None
            )
            status = "success" if transmit_result.get("code") == 0 else "error"
            err = None if status == "success" else transmit_result.get("message")
        except Exception as e:
            logger.error(f"Centrala transmission failed: {e}")
            return RunTaskResponse(
                status="error",
                session_id=session_id,
                city_name=city_name,
                city_area=formatted_area,
                warehouses_count=warehouses_count,
                phone_number=phone_number,
                error=f"Transmission failed: {e}",
            )

        return RunTaskResponse(
            status=status,
            session_id=session_id,
            city_name=city_name,
            city_area=formatted_area,
            warehouses_count=warehouses_count,
            phone_number=phone_number,
            secret_flag=secret_flag,
            mission_flag=mission_flag,
            error=err,
        )
