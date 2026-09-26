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
    """Generates standardized session ID: s05e01_{backend}_{YYYYMMDD_HHMMSS} (Europe/Zurich)."""
    now = datetime.now(ZURICH_TZ).strftime("%Y%m%d_%H%M%S")
    return f"s05e01_{backend}_{now}"


def mask_binary_output(data: Any) -> Any:
    """Masks long Base64 strings in dictionaries or lists to comply with Zero-Pollution telemetry rules."""
    if isinstance(data, dict):
        masked = {}
        for k, v in data.items():
            if (
                k in ("attachment", "content_base64", "base64", "bytes")
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
    """Real-time auditing service streaming interaction steps and signal telemetry directly to BigQuery."""

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
        """Immediately log an interaction step to BigQuery with safe fallbacks."""
        now_iso = datetime.now(ZURICH_TZ).isoformat()
        sanitized_meta = mask_binary_output(metadata or {})
        if step_type:
            sanitized_meta["step_type"] = step_type
        if flag:
            sanitized_meta["flag"] = flag

        clean_content = content[:1500] if content else ""
        if len(clean_content) > 200 and re.fullmatch(
            r"[A-Za-z0-9+/=]+", clean_content[:100]
        ):
            clean_content = f"<REDACTED_BASE64: {len(content)} chars>"

        row = {
            "timestamp": now_iso,
            "session_id": session_id,
            "actor": actor,
            "content": clean_content,
            "metadata": json.dumps(sanitized_meta, ensure_ascii=False),
        }

        def _insert():
            try:
                errors = self.client.insert_rows_json(self.full_table_id, [row])
                if errors:
                    logger.warning(
                        f"Failed to insert audit event into BigQuery: {errors}"
                    )
            except Exception as e:
                logger.debug(
                    f"BigQuery logging skipped/failed ({e}). Row: {actor} - {clean_content[:100]}"
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
        model_name = serialized.get("name") or serialized.get("id", ["unknown"])[-1]
        prompt_preview = prompts[0][:300] if prompts else ""
        await self.audit.log_event(
            session_id=self.session_id,
            actor="agent",
            content=f"LLM Call started: {model_name} | {prompt_preview}",
            step_type="llm_start",
            metadata={"model": model_name, "prompt_count": len(prompts)},
        )

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        text = ""
        if response.generations and response.generations[0]:
            text = response.generations[0][0].text
        await self.audit.log_event(
            session_id=self.session_id,
            actor="agent",
            content=f"LLM Response: {text[:400]}",
            step_type="llm_end",
        )

    async def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        tool_name = serialized.get("name", "unknown_tool")
        sanitized_input = mask_binary_output(input_str)
        await self.audit.log_event(
            session_id=self.session_id,
            actor="tool",
            content=f"Tool {tool_name} invoked: {str(sanitized_input)[:300]}",
            step_type="tool_start",
            metadata={"tool": tool_name},
        )

    async def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        output_str = str(output)
        clean_output = str(mask_binary_output(output_str))
        await self.audit.log_event(
            session_id=self.session_id,
            actor="tool",
            content=f"Tool Output: {clean_output[:400]}",
            step_type="tool_end",
        )
