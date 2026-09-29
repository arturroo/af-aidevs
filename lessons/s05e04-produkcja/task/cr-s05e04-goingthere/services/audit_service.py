"""Audit and telemetry service streaming events directly to BigQuery."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from google.cloud import bigquery

from config import config

logger = logging.getLogger("services.audit")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


def generate_session_id(prefix: str = "fsm") -> str:
    """Generates standardized session ID: s05e04_{prefix}_{YYYYMMDD_HHMMSS}."""
    now = datetime.now(ZURICH_TZ).strftime("%Y%m%d_%H%M%S")
    return f"s05e04_{prefix}_{now}"


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
    """Real-time auditing service streaming flight telemetry to BigQuery."""

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
                    description="Entity emitting the log: system, flight_controller, radar_service, or navigator",
                ),
                bigquery.SchemaField(
                    "content",
                    "STRING",
                    mode="NULLABLE",
                    description="Sanitized event details or telemetry preview",
                ),
                bigquery.SchemaField(
                    "metadata",
                    "JSON",
                    mode="NULLABLE",
                    description="Structured telemetry metadata (column, row, action, rock_row, latency)",
                ),
            ]
            table = bigquery.Table(self.full_table_id, schema=schema)
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="timestamp",
            )
            self.client.create_table(table, exists_ok=True)
            logger.info(f"Audit table verified/created: {self.full_table_id}")
        except Exception as e:
            logger.warning(
                f"Could not initialize BigQuery audit table {self.full_table_id}: {e}"
            )

    def log_event(
        self,
        session_id: str,
        actor: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Synchronously streams an audit event row into BigQuery."""
        now_utc = datetime.now(UTC).isoformat()
        sanitized_content = sanitize_audit_content(content)
        row = {
            "timestamp": now_utc,
            "session_id": session_id,
            "actor": actor,
            "content": sanitized_content,
            "metadata": json.dumps(metadata or {}),
        }
        try:
            errors = self.client.insert_rows_json(self.full_table_id, [row])
            if errors:
                logger.error(f"Failed to stream audit event to BigQuery: {errors}")
        except Exception as e:
            logger.debug(f"Audit event streaming skipped or failed: {e}")

    async def alog_event(
        self,
        session_id: str,
        actor: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Asynchronously streams an audit event row into BigQuery via threadpool."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self.log_event, session_id, actor, content, metadata
        )
