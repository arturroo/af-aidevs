import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from zoneinfo import ZoneInfo
from google.cloud import bigquery
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult
import config

logger = logging.getLogger("services.audit")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


class AuditService:
    """Real-time auditing service logging every interaction step directly to BigQuery."""

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
            self._client = bigquery.Client(project=self.project_id, location=self.location)
        return self._client

    async def log_event(
        self,
        session_id: str,
        actor: str,
        content: str,
        step_type: str = "general",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Immediately log an interaction step before the next action proceeds."""
        def _insert():
            timestamp = datetime.now(ZURICH_TZ).isoformat()
            meta_dict = metadata or {}
            if "step_type" not in meta_dict:
                meta_dict["step_type"] = step_type

            row = {
                "timestamp": timestamp,
                "session_id": session_id,
                "actor": actor,
                "content": str(content),
                "metadata": json.dumps(meta_dict),
                "step_type": step_type,
                "reasoning": str(content),
                "payload": json.dumps(meta_dict),
            }

            try:
                errors = self.client.insert_rows_json(
                    self.full_table_id,
                    [row],
                    ignore_unknown_values=True,
                )
                if errors:
                    logger.error(f"[BigQuery Audit Error] {self.full_table_id}: {errors}")
            except Exception as e:
                logger.warning(f"[BigQuery Audit Fallback] {e}")
                print(json.dumps({"audit_event": row}), flush=True)

        await asyncio.to_thread(_insert)


class BigQueryCallbackHandler(AsyncCallbackHandler):
    """LangChain callback handler that logs LLM calls, tool runs, and errors immediately to BigQuery."""

    def __init__(self, audit_service: AuditService, session_id: str):
        super().__init__()
        self.audit = audit_service
        self.session_id = session_id

    async def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        prompt_text = prompts[0] if prompts else str(serialized)
        await self.audit.log_event(
            session_id=self.session_id,
            actor="user",
            content=prompt_text,
            step_type="llm_input",
            metadata={"serialized": serialized.get("name", "llm")},
        )

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        text = ""
        if response.generations and response.generations[0]:
            text = response.generations[0][0].text
        await self.audit.log_event(
            session_id=self.session_id,
            actor="model",
            content=text or "LLM response generated",
            step_type="llm_output",
            metadata={"llm_output": str(response.llm_output)},
        )

    async def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        tool_name = serialized.get("name", "unknown_tool")
        await self.audit.log_event(
            session_id=self.session_id,
            actor="agent",
            content=f"Invoking tool: {tool_name} with input: {input_str}",
            step_type="tool_call",
            metadata={"tool": tool_name, "input": input_str},
        )

    async def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        await self.audit.log_event(
            session_id=self.session_id,
            actor="tool",
            content=str(output),
            step_type="tool_result",
            metadata={"output_len": len(str(output))},
        )

    async def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        await self.audit.log_event(
            session_id=self.session_id,
            actor="tool",
            content=f"Tool error: {str(error)}",
            step_type="tool_error",
            metadata={"error_type": type(error).__name__},
        )
