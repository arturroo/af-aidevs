import asyncio
import json
import logging
import re
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
    """Generates standardized session ID: s05e02_{backend}_{YYYYMMDD_HHMMSS} (Europe/Zurich)."""
    now = datetime.now(ZURICH_TZ).strftime("%Y%m%d_%H%M%S")
    return f"s05e02_{backend}_{now}"


def mask_binary_output(data: Any) -> Any:
    """Masks long Base64 strings in dictionaries or lists to comply with Zero-Pollution telemetry rules."""
    if isinstance(data, dict):
        masked = {}
        for k, v in data.items():
            if (
                k in ("audio", "attachment", "content_base64", "base64", "bytes")
                and isinstance(v, str)
                and len(v) > 100
            ):
                masked[k] = (
                    f"<REDACTED_BASE64: {len(v)} chars, ~{len(v) * 3 // 4 // 1024} KB>"
                )
            else:
                masked[k] = mask_binary_output(v)
        return masked
    if isinstance(data, list):
        return [mask_binary_output(item) for item in data]
    if (
        isinstance(data, str)
        and len(data) > 500
        and re.fullmatch(r"[A-Za-z0-9+/=]+", data[:200])
    ):
        return f"<REDACTED_BASE64: {len(data)} chars>"
    return data


class AuditService:
    """Real-time auditing service streaming phonecall interaction turns and telemetry directly to BigQuery."""

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
                    description="Entity emitting the log: system, orchestrator, agent, or operator",
                ),
                bigquery.SchemaField(
                    "content",
                    "STRING",
                    mode="NULLABLE",
                    description="Sanitized event details or message preview",
                ),
                bigquery.SchemaField(
                    "metadata",
                    "JSON",
                    mode="NULLABLE",
                    description="Structured telemetry metadata (objective, sentiments, road status)",
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
        sanitized_content = content[:1500] if content else ""
        sanitized_meta = mask_binary_output(metadata or {})

        row = {
            "timestamp": now_iso,
            "session_id": session_id,
            "actor": actor,
            "content": sanitized_content,
            "metadata": json.dumps(sanitized_meta, ensure_ascii=False),
        }

        try:
            errors = self.client.insert_rows_json(self.full_table_id, [row])
            if errors:
                logger.warning(
                    f"BigQuery insert error for {self.full_table_id}: {errors}"
                )
        except Exception as e:
            logger.warning(
                f"Could not log event to BigQuery ({self.full_table_id}): {e}"
            )

    async def alog_event(
        self,
        session_id: str,
        actor: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Asynchronously dispatches an audit event to BigQuery in an executor thread."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self.log_event, session_id, actor, content, metadata
        )


class BigQueryCallbackHandler(AsyncCallbackHandler):
    """LangChain callback streaming LLM prompts and generations to BigQuery audit."""

    def __init__(self, audit_service: AuditService, session_id: str) -> None:
        super().__init__()
        self.audit = audit_service
        self.session_id = session_id

    async def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        for prompt in prompts:
            preview = prompt[:300].replace("\n", " ")
            await self.audit.alog_event(
                session_id=self.session_id,
                actor="llm_prompt",
                content=preview,
                metadata={"length": len(prompt)},
            )

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        for generations in response.generations:
            for gen in generations:
                preview = gen.text[:300].replace("\n", " ")
                await self.audit.alog_event(
                    session_id=self.session_id,
                    actor="llm_response",
                    content=preview,
                    metadata={"length": len(gen.text)},
                )
