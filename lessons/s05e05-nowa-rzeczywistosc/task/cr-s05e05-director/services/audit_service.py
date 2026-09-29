import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from google.cloud import bigquery

from config import settings

logger = logging.getLogger("services.audit")


def generate_session_id(prefix: str = "timetravel") -> str:
    """Generates standardized session ID: s05e05_{prefix}_{YYYYMMDD_HHMMSS}."""
    now = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"s05e05_{prefix}_{now}"


def sanitize_audit_content(content: str, max_chars: int = 1500) -> str:
    """Sanitizes content to prevent telemetry bloat while keeping essential diagnostics."""
    if not content:
        return ""
    if len(content) > max_chars:
        return content[:max_chars] + f"\n... [TRUNCATED: total {len(content)} chars]"
    return content


class AuditService:
    """Real-time auditing service streaming mission telemetry directly to BigQuery."""

    def __init__(
        self,
        dataset_id: str = settings.BIGQUERY_DATASET,
        table_id: str = settings.BIGQUERY_TABLE,
        project_id: str | None = None,
        location: str = settings.GOOGLE_CLOUD_LOCATION,
    ) -> None:
        self.project_id = project_id or settings.GOOGLE_CLOUD_PROJECT
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
        """Verifies that the audit table exists, creating it if needed."""
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
                    description="Unique execution session ID",
                ),
                bigquery.SchemaField(
                    "actor",
                    "STRING",
                    mode="REQUIRED",
                    description="System actor (director, cockpit, central)",
                ),
                bigquery.SchemaField(
                    "phase",
                    "INT64",
                    mode="NULLABLE",
                    description="Mission phase (1, 2, 3)",
                ),
                bigquery.SchemaField(
                    "event_type",
                    "STRING",
                    mode="REQUIRED",
                    description="Action type",
                ),
                bigquery.SchemaField(
                    "content",
                    "STRING",
                    mode="REQUIRED",
                    description="Diagnostic payload summary",
                ),
                bigquery.SchemaField(
                    "latency_ms",
                    "FLOAT64",
                    mode="NULLABLE",
                    description="Duration of step in ms",
                ),
                bigquery.SchemaField(
                    "metadata",
                    "JSON",
                    mode="NULLABLE",
                    description="Additional structured context",
                ),
            ]

            dataset_ref = bigquery.DatasetReference(self.project_id, self.dataset_id)
            try:
                self.client.get_dataset(dataset_ref)
            except Exception:
                dataset = bigquery.Dataset(dataset_ref)
                dataset.location = "europe-west1"
                self.client.create_dataset(dataset, exists_ok=True)
                logger.info("Created BigQuery dataset: %s", self.dataset_id)

            table = bigquery.Table(self.full_table_id, schema=schema)
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="timestamp",
            )
            table.clustering_fields = ["session_id", "actor"]
            self.client.create_table(table, exists_ok=True)
            logger.info("Ensured BigQuery table exists: %s", self.full_table_id)
        except Exception as e:
            logger.warning(
                "Unable to create/verify BigQuery table %s: %s",
                self.full_table_id,
                e,
            )

    async def log_event(
        self,
        session_id: str,
        actor: str,
        event_type: str,
        content: str,
        phase: int | None = None,
        latency_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Asynchronously streams a single audit event row into BigQuery."""
        now_utc = datetime.now(UTC).isoformat()
        clean_content = sanitize_audit_content(content)
        meta_dict: dict[str, Any] = {
            "phase": phase,
            "event_type": event_type,
            "latency_ms": latency_ms,
            **(metadata or {}),
        }
        row = {
            "timestamp": now_utc,
            "session_id": session_id,
            "actor": actor,
            "content": clean_content,
            "metadata": json.dumps(meta_dict),
        }

        def _insert() -> None:
            try:
                errors = self.client.insert_rows_json(
                    self.full_table_id, [row], ignore_unknown_values=True
                )
                if errors:
                    logger.warning(
                        "BigQuery insert errors on %s: %s",
                        self.full_table_id,
                        errors,
                    )
            except Exception as ex:
                logger.debug("BigQuery streaming exception (safe fallback): %s", ex)

        try:
            await asyncio.to_thread(_insert)
        except Exception as e:
            logger.debug("Failed to spawn thread for BigQuery log: %s", e)


audit_service = AuditService()
