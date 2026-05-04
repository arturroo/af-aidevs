import os
import json
import logging
import asyncio
from typing import Dict, Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from google.cloud import bigquery

logger = logging.getLogger(__name__)

BQ_AUDIT_TABLE = os.getenv("BQ_AUDIT_TABLE") or "af-aidevs.s01e05.audit"
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT") or "af-aidevs"
ZURICH_TZ = ZoneInfo("Europe/Zurich")

bq_client = bigquery.Client(project=GOOGLE_CLOUD_PROJECT, location="europe-west6")

async def log_to_bq(session_id: str, actor: str, content: str, metadata: Optional[Dict] = None):
    """Audits interaction to BigQuery asynchronously."""
    def _do_insert():
        try:
            row = {
                "timestamp": datetime.now(ZURICH_TZ).isoformat(),
                "session_id": session_id,
                "actor": actor,
                "content": content,
                "metadata": json.dumps(metadata) if metadata else None
            }
            if BQ_AUDIT_TABLE and "." in BQ_AUDIT_TABLE:
                errors = bq_client.insert_rows_json(BQ_AUDIT_TABLE, [row])
                if errors:
                    logger.error(f"BQ Audit Error: {errors}")
            else:
                logger.info(f"[Audit Log] {actor}: {content[:100]}...")
        except Exception as e:
            logger.error(f"Failed to log to BQ: {e}")

    await asyncio.to_thread(_do_insert)
