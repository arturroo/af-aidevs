"""Real-time BigQuery telemetry and audit logging service."""

import asyncio
from datetime import datetime
import json
import logging
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo
from google.cloud import bigquery
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

import config

logger = logging.getLogger("services.audit")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


def generate_session_id(backend: str = "langchain") -> str:
    """Generates standardized session ID: s03e04_{backend}_{YYYYMMDD_HHMMSS} (Europe/Zurich)."""
    now = datetime.now(ZURICH_TZ).strftime("%Y%m%d_%H%M%S")
    return f"s03e04_{backend}_{now}"


class AuditService:
    """Real-time auditing service streaming interaction steps and tool telemetry directly to BigQuery."""

    def __init__(
        self,
        dataset_id: str = config.BQ_DATASET,
        table_id: str = config.BQ_TABLE,
        project_id: Optional[str] = None,
        location: str = config.GOOGLE_CLOUD_LOCATION,
    ):
        self.project_id = project_id or config.GOOGLE_CLOUD_PROJECT
        self.dataset_id = dataset_id
        self.table_id = table_id
        self.location = location
        self.full_table_id = f"{self.project_id}.{self.dataset_id}.{self.table_id}"
        self._client: Optional[bigquery.Client] = None

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
        metadata: Optional[Dict[str, Any]] = None,
        flag: Optional[str] = None,
    ):
        """Immediately log an interaction step to BigQuery with stdout fallback."""

        def _insert():
            timestamp = datetime.now(ZURICH_TZ).isoformat()
            meta_dict = metadata or {}
            meta_str = (
                json.dumps(meta_dict, ensure_ascii=False)
                if isinstance(meta_dict, dict)
                else str(meta_dict)
            )

            row = {
                "timestamp": timestamp,
                "session_id": session_id,
                "actor": actor,
                "action": step_type,
                "details": meta_str,
                "content": content,
                "step_type": step_type,
                "metadata": meta_str,
                "flag": flag,
            }

            try:
                errors = self.client.insert_rows_json(
                    self.full_table_id, [row], ignore_unknown_values=True
                )
                if errors:
                    logger.warning("BigQuery insertion error: %s", errors)
                else:
                    logger.debug("Logged audit step to BigQuery for session %s", session_id)
            except Exception as e:
                logger.warning(
                    "Could not stream log to BigQuery table %s: %s", self.full_table_id, e
                )

        try:
            await asyncio.to_thread(_insert)
        except Exception as e:
            logger.error("Failed to run async audit logging: %s", e)


class BigQueryCallbackHandler(AsyncCallbackHandler):
    """LangChain lifecycle hook streaming LLM and tool events to BigQuery."""

    def __init__(self, audit_service: AuditService, session_id: str):
        super().__init__()
        self.audit = audit_service
        self.session_id = session_id

    async def on_llm_start(
        self, serialized: Dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        content = "\n".join(prompts)
        await self.audit.log_event(
            session_id=self.session_id,
            actor="model",
            content=f"[LLM Start] {content[:300]}...",
            step_type="llm_start",
            metadata={"serialized": str(serialized)},
        )

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        generations = response.generations
        first_gen = (
            generations[0][0].text if generations and generations[0] else "empty"
        )
        await self.audit.log_event(
            session_id=self.session_id,
            actor="model",
            content=f"[LLM End] {first_gen[:300]}...",
            step_type="llm_end",
        )

    async def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        tool_name = serialized.get("name", "unknown_tool")
        await self.audit.log_event(
            session_id=self.session_id,
            actor="tool",
            content=f"[Tool Start: {tool_name}] Input: {input_str[:300]}",
            step_type="tool_start",
            metadata={"tool_name": tool_name},
        )

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        await self.audit.log_event(
            session_id=self.session_id,
            actor="tool",
            content=f"[Tool End] Output: {output[:300]}",
            step_type="tool_end",
        )

    async def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        err_msg = str(error)
        if len(err_msg) > 300:
            err_msg = err_msg[:300] + "..."
        await self.audit.log_event(
            session_id=self.session_id,
            actor="tool",
            content=f"[Tool Error] {err_msg}",
            step_type="tool_error",
        )
