import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from google.cloud import bigquery
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

import config

logger = logging.getLogger("services.audit")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


def generate_session_id(backend: str = "langchain") -> str:
    """Generates standardized session ID: s04e05_{backend}_{YYYYMMDD_HHMMSS} (Europe/Zurich)."""
    now = datetime.now(ZURICH_TZ).strftime("%Y%m%d_%H%M%S")
    return f"s04e05_{backend}_{now}"


class AuditService:
    """Real-time auditing service streaming interaction steps and tool telemetry directly to BigQuery."""

    def __init__(
        self,
        dataset_id: str = config.BQ_DATASET,
        table_id: str = config.BQ_TABLE,
        project_id: str | None = None,
        location: str = config.GOOGLE_CLOUD_LOCATION,
    ):
        self.project_id = project_id or config.GOOGLE_CLOUD_PROJECT
        self.dataset_id = dataset_id
        self.table_id = table_id
        self.location = location
        self.full_table_id = f"{self.project_id}.{self.dataset_id}.{self.table_id}"
        self._client: bigquery.Client | None = None

    @property
    def client(self) -> bigquery.Client:
        if self._client is None:
            self._client = bigquery.Client(
                project=self.project_id, location=self.location
            )
        return self._client

    async def log_event(
        self,
        session_id: str,
        actor: str,
        content: str,
        step_type: str = "general",
        metadata: dict[str, Any] | None = None,
        flag: str | None = None,
    ):
        """Immediately log an interaction step to BigQuery with stdout fallback."""
        now_iso = datetime.now(ZURICH_TZ).isoformat()
        meta = dict(metadata or {})
        if step_type:
            meta["step_type"] = step_type
        if flag:
            meta["flag"] = flag

        row = {
            "timestamp": now_iso,
            "session_id": session_id,
            "actor": actor,
            "content": content[:1500] if content else "",
            "metadata": json.dumps(meta, ensure_ascii=False),
        }

        # Non-blocking streaming insert
        def _insert():
            try:
                errors = self.client.insert_rows_json(self.full_table_id, [row])
                if errors:
                    logger.warning(
                        f"Failed to insert audit event into BigQuery: {errors}"
                    )
            except Exception as e:
                logger.debug(
                    f"BigQuery logging skipped/failed ({e}). Row: {actor} - {content[:100]}"
                )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _insert)


class AuditCallbackHandler(AsyncCallbackHandler):
    """LangChain callback streaming model events to BigQuery and LangSmith."""

    def __init__(self, audit_service: AuditService, session_id: str):
        super().__init__()
        self.audit = audit_service
        self.session_id = session_id

    async def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        await asyncio.sleep(1.0)
        prompt_snippet = prompts[0][:300] if prompts else ""
        await self.audit.log_event(
            session_id=self.session_id,
            actor="agent:llm",
            content=f"LLM Prompt: {prompt_snippet}",
            step_type="prompt",
        )

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        text = (
            response.generations[0][0].text
            if response.generations and response.generations[0]
            else ""
        )
        await self.audit.log_event(
            session_id=self.session_id,
            actor="agent:llm",
            content=f"LLM Output: {text[:500]}",
            step_type="completion",
        )

    async def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        tool_name = serialized.get("name", "tool")
        await self.audit.log_event(
            session_id=self.session_id,
            actor=f"tool:{tool_name}",
            content=f"Tool Start: {input_str[:400]}",
            step_type="tool_input",
        )

    async def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        out_str = str(output)
        flag = None
        if "{FLG:" in out_str:
            import re

            m = re.search(r"\{FLG:[^}]+\}", out_str)
            if m:
                flag = m.group(0)

        await self.audit.log_event(
            session_id=self.session_id,
            actor="tool:output",
            content=f"Tool Output: {out_str[:400]}",
            step_type="tool_output",
            flag=flag,
        )
