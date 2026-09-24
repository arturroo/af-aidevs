"""Real-time BigQuery telemetry and audit logging service for S04E04."""

import asyncio
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
    """Generates standardized session ID: s04e04_{backend}_{YYYYMMDD_HHMMSS} (Europe/Zurich)."""
    now = datetime.now(ZURICH_TZ).strftime("%Y%m%d_%H%M%S")
    return f"s04e04_{backend}_{now}"


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
        preview = (content[:200] + "...") if len(content) > 200 else content
        logger.info(f"[{session_id}] [{actor}] ({step_type}) {preview}")

        row = {
            "timestamp": now_iso,
            "session_id": session_id,
            "actor": actor,
            "content": content[:5000],  # Guardrail against overly long content dumps
        }

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._insert_row_sync, row)
        except Exception as e:
            logger.warning(f"Failed to stream audit log to BigQuery: {e}")

    def _insert_row_sync(self, row: dict[str, Any]):
        try:
            errors = self.client.insert_rows_json(self.full_table_id, [row])
            if errors:
                logger.error(f"BigQuery streaming insert errors: {errors}")
        except Exception as e:
            logger.warning(f"BigQuery streaming error: {e}")


class AuditCallbackHandler(AsyncCallbackHandler):
    """LangChain async callback handler for recording LLM and tool operations into AuditService."""

    def __init__(self, audit_service: AuditService, session_id: str):
        super().__init__()
        self.audit = audit_service
        self.session_id = session_id

    async def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        pass

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        pass

    async def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        tool_name = serialized.get("name", "unknown_tool")
        await self.audit.log_event(
            session_id=self.session_id,
            actor=f"tool_start:{tool_name}",
            content=input_str,
            step_type="tool_start",
        )

    async def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        out_str = str(output)
        if len(out_str) > 1000:
            out_str = out_str[:1000] + " ... [TRUNCATED]"
        await self.audit.log_event(
            session_id=self.session_id,
            actor="tool_end",
            content=out_str,
            step_type="tool_end",
        )

    async def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        await self.audit.log_event(
            session_id=self.session_id,
            actor="tool_error",
            content=str(error),
            step_type="tool_error",
        )
