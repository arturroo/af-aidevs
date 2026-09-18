"""Real-time BigQuery telemetry and audit logging service for S04E01."""

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
    """Generates standardized session ID: s04e01_{backend}_{YYYYMMDD_HHMMSS} (Europe/Zurich)."""
    now = datetime.now(ZURICH_TZ).strftime("%Y%m%d_%H%M%S")
    return f"s04e01_{backend}_{now}"


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

        def _insert():
            timestamp = datetime.now(ZURICH_TZ).isoformat()
            meta_dict = metadata or {}

            # Redact flag in public logs/BigQuery preview if present
            safe_flag = "{FLG:...}" if flag and "{FLG:" in flag else flag

            if isinstance(meta_dict, dict):
                meta_dict = {
                    **meta_dict,
                    "action": step_type,
                    "step_type": step_type,
                    "flag": safe_flag,
                }
                meta_str = json.dumps(meta_dict, ensure_ascii=False)
            else:
                meta_str = str(meta_dict)

            row = {
                "timestamp": timestamp,
                "session_id": session_id,
                "actor": actor,
                "content": content[:2000],
                "metadata": meta_str[:2000],
            }

            try:
                table = self.client.get_table(self.full_table_id)
                errors = self.client.insert_rows_json(table, [row])
                if errors:
                    logger.warning(
                        f"BigQuery streaming insert errors for {self.full_table_id}: {errors}"
                    )
            except Exception as e:
                logger.debug(
                    f"Direct BigQuery logging failed, falling back to stdout: {e}"
                )
                print(
                    f"[AUDIT-FALLBACK] {timestamp} | {session_id} | {actor} | {step_type}: {content[:200]}"
                )

        try:
            await asyncio.to_thread(_insert)
        except Exception as e:
            logger.debug(f"Async BigQuery log failed: {e}")


class BigQueryCallbackHandler(AsyncCallbackHandler):
    """LangChain callback handler streaming LLM events and tool invocations to BigQuery."""

    def __init__(self, audit_service: AuditService, session_id: str):
        super().__init__()
        self.audit = audit_service
        self.session_id = session_id

    async def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        first_prompt = prompts[0] if prompts else ""
        await self.audit.log_event(
            session_id=self.session_id,
            actor="model",
            content=first_prompt[:500],
            step_type="llm_start",
            metadata={"serialized": str(serialized)[:200]},
        )

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        text = ""
        if response.generations and response.generations[0]:
            text = response.generations[0][0].text
        await self.audit.log_event(
            session_id=self.session_id,
            actor="model",
            content=text[:500],
            step_type="llm_end",
        )

    async def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        tool_name = serialized.get("name", "unknown_tool")
        await self.audit.log_event(
            session_id=self.session_id,
            actor=f"tool:{tool_name}",
            content=input_str[:500],
            step_type="tool_start",
        )

    async def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        await self.audit.log_event(
            session_id=self.session_id,
            actor="tool",
            content=str(output)[:500],
            step_type="tool_end",
        )
