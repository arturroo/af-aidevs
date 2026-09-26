import logging
from abc import ABC, abstractmethod

from schemas import ObjectFinding
from services.audit_service import AuditService
from services.mcp_service import MCPService
from services.model_armor_service import ModelArmorService

logger = logging.getLogger("agents.base")

DUAL_OBJECTIVE_INSTRUCTIONS = """
DUAL SEARCH OBJECTIVES:
1. PRIMARY MISSION (SYJON RECONNAISSANCE):
   Find all facts regarding the hidden resistance settlement known colloquially as "Syjon":
   - Real administrative name of the city (e.g. Opalino, Grudziadz, etc.)
   - Surface/administrative area of the city (numbers, units km², square kilometers)
   - Total number/count of warehouses in Syjon
   - Contact phone number for the city liaison
2. SECONDARY MISSION (SECRET TELEGRAPHIST HUNTER):
   Actively scan for any clues, notes, records, or rhythms referring to:
   - Julian Tuwim's "Piosenka telegrafisty" (or keywords: telegrafista, telegraf, stukanie, domatowo)
   - Morse code representation of the word 'FLAGA': F (..-.), L (.-..), A (.-), G (--.), A (.-) -> (··−·  ·−··  ·−  −−·  ·−)
   - Any secret flag formatted as {FLG:...} or secondary mission code
"""


class BaseSubagent(ABC):
    """Abstract base class for all specialized multimodal subagents."""

    def __init__(
        self,
        mcp_service: MCPService,
        audit_service: AuditService | None = None,
        model_armor_service: ModelArmorService | None = None,
        model_name: str | None = None,
    ):
        self.mcp = mcp_service
        self.audit = audit_service
        self.model_armor = model_armor_service
        self.model_name = model_name

    @abstractmethod
    async def analyze(
        self, session_id: str, file_path: str, mime_type: str
    ) -> ObjectFinding:
        """Analyzes a decoded artifact and produces a structured ObjectFinding."""

    async def save_finding(self, session_id: str, finding: ObjectFinding) -> str:
        """Saves typed finding to /findings/{source_file}.json in cr-mcp-workspace."""
        clean_source = finding.source_file.lstrip("/")
        if clean_source.startswith("decoded/"):
            rel_name = clean_source[len("decoded/") :]
        else:
            rel_name = clean_source

        finding_path = f"/findings/{rel_name}.json"
        content_json = finding.model_dump_json(indent=2)
        await self.mcp.write_file(session_id, finding_path, content_json)

        if self.audit:
            preview = (
                finding.summary_sentences[0]
                if finding.summary_sentences
                else "No summary"
            )
            await self.audit.log_event(
                session_id=session_id,
                actor="subagent",
                content=f"Saved finding for {finding.source_file}: {preview[:150]}",
                step_type="finding_saved",
                metadata={"finding_path": finding_path, "mime": finding.mime_type},
            )
        return finding_path
