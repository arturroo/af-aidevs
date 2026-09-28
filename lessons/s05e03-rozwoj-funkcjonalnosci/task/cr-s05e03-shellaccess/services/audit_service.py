"""Audit and telemetry service streaming events directly to BigQuery."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from google.cloud import bigquery
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from config import config

logger = logging.getLogger("services.audit")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


def generate_session_id(backend: str = "langchain") -> str:
    """Generates standardized session ID: s05e03_{backend}_{YYYYMMDD_HHMMSS}."""
    now = datetime.now(ZURICH_TZ).strftime("%Y%m%d_%H%M%S")
    return f"s05e03_{backend}_{now}"


def sanitize_audit_content(content: str, max_chars: int = 2000) -> str:
    """Sanitizes content to prevent log pollution while keeping essential diagnostics."""
    if not content:
        return ""
    if len(content) > max_chars:
        return (
            content[:max_chars]
            + f"\n... [TRUNCATED FOR AUDIT: total {len(content)} chars]"
        )
    return content


class AuditService:
    """Real-time auditing service streaming shell interactions and agent telemetry to BigQuery."""

    def __init__(
        self,
        dataset_id: str = config.BQ_DATASET,
        table_id: str = config.BQ_TABLE,
        project_id: str | None = None,
        location: str = config.GOOGLE_CLOUD_LOCATION,
    ) -> None:
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

    def ensure_table(self) -> None:
        """Verifies that the audit table exists with the canonical schema, creating it if needed."""
        try:
            schema = [
                bigquery.SchemaField(
                    "timestamp",
                    "TIMESTAMP",
                    mode="REQUIRED",
                    description="Event timestamp in UTC",
                ),
                bigquery.SchemaField(
                    "session_id",
                    "STRING",
                    mode="REQUIRED",
                    description="Unique conversation session run ID",
                ),
                bigquery.SchemaField(
                    "actor",
                    "STRING",
                    mode="REQUIRED",
                    description="Entity emitting the log: system, orchestrator, agent, or repl",
                ),
                bigquery.SchemaField(
                    "content",
                    "STRING",
                    mode="NULLABLE",
                    description="Sanitized event details or command output preview",
                ),
                bigquery.SchemaField(
                    "metadata",
                    "JSON",
                    mode="NULLABLE",
                    description="Structured telemetry metadata (cmd, verdict, latency, exit_code)",
                ),
            ]
            table = bigquery.Table(self.full_table_id, schema=schema)
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="timestamp",
            )
            self.client.create_table(table, exists_ok=True)
            logger.info(f"BigQuery audit table verified/ready: {self.full_table_id}")
        except Exception as e:
            logger.warning(
                f"Audit table check/creation skipped or failed: {e}. Audit logging will attempt inserts directly."
            )

    def log_event(
        self,
        session_id: str,
        actor: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Inserts an audit event synchronously into BigQuery."""
        now_iso = datetime.now(ZoneInfo("UTC")).isoformat()
        sanitized_content = sanitize_audit_content(content)
        sanitized_meta = metadata or {}

        row = {
            "timestamp": now_iso,
            "session_id": session_id,
            "actor": actor,
            "content": sanitized_content,
            "metadata": json.dumps(sanitized_meta, default=str),
        }

        try:
            errors = self.client.insert_rows_json(self.full_table_id, [row])
            if errors:
                logger.error(f"Failed to stream audit log to BigQuery: {errors}")
        except Exception as e:
            logger.warning(f"Error streaming audit log row to BigQuery: {e}")

    async def alog_event(
        self,
        session_id: str,
        actor: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Asynchronously streams an audit log row to BigQuery using loop executor."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self.log_event, session_id, actor, content, metadata
        )


class AuditCallbackHandler(AsyncCallbackHandler):
    """LangChain callback handler recording LLM token telemetry and agent events to BigQuery."""

    def __init__(self, audit_service: AuditService, session_id: str) -> None:
        super().__init__()
        self.audit_service = audit_service
        self.session_id = session_id

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            usage = (
                response.llm_output.get("token_usage", {})
                if response.llm_output
                else {}
            )
            await self.audit_service.alog_event(
                session_id=self.session_id,
                actor="agent_llm",
                content="LLM generation completed",
                metadata={"token_usage": usage},
            )
        except Exception as e:
            logger.debug(f"AuditCallbackHandler failed on on_llm_end: {e}")
