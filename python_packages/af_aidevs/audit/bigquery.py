import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from google.cloud import bigquery

logger = logging.getLogger("af_aidevs.audit.bigquery")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


class BigQueryAuditService:
    """Service to asynchronously log audit records to Google BigQuery."""

    def __init__(
        self,
        dataset_id: str,
        table_id: str = "audit",
        project_id: Optional[str] = None,
        location: str = "europe-west6",
    ):
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or "af-aidevs"
        self.dataset_id = dataset_id
        self.table_id = table_id
        self.location = location
        self.full_table_id = f"{self.project_id}.{self.dataset_id}.{self.table_id}"
        self._client: Optional[bigquery.Client] = None

    @property
    def client(self) -> bigquery.Client:
        if self._client is None:
            self._client = bigquery.Client(project=self.project_id, location=self.location)
        return self._client

    async def log(
        self,
        session_id: str,
        actor: str,
        step_type: str,
        reasoning: str,
        payload: Optional[Dict[str, Any]] = None,
        flag: Optional[str] = None,
    ):
        """Asynchronously insert an audit record into BigQuery."""
        def _insert_sync():
            timestamp = datetime.now(ZURICH_TZ).isoformat()
            meta = {
                "step_type": step_type,
                "payload": payload,
                "flag": flag,
            }
            row = {
                "timestamp": timestamp,
                "session_id": session_id,
                "actor": actor,
                "content": reasoning,
                "metadata": json.dumps(meta),
                "step_type": step_type,
                "reasoning": reasoning,
                "payload": json.dumps(payload) if payload is not None else None,
                "flag": flag,
            }
            try:
                errors = self.client.insert_rows_json(
                    self.full_table_id,
                    [row],
                    ignore_unknown_values=True,
                )
                if errors:
                    logger.error(f"[BigQuery Audit Error] Table {self.full_table_id}: {errors}")
            except Exception as e:
                logger.warning(f"[BigQuery Audit Fallback] Could not log to {self.full_table_id}: {e}")
                # Emit structured log to stdout for Log Sink fallback
                print(json.dumps({"log_type": "AUDIT_FALLBACK", **row}), flush=True)

        await asyncio.to_thread(_insert_sync)
