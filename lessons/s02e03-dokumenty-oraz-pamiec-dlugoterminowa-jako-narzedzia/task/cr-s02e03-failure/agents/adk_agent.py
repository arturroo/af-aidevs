import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo
from google import genai
from af_aidevs.utils.prompts import load_system_prompt
import config
from schemas import RunTaskResponse
from services.audit_service import AuditService
from services.token_service import TokenService
from services.failure_service import FailureLogProcessor
from services.mcp_service import MCPService

logger = logging.getLogger("agents.adk")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


class ADKFailureAgent:
    """Google GenAI SDK implementation on Vertex AI with zero-trust MCP isolation and streaming BigQuery auditing."""

    def __init__(self):
        self.prompt_config = load_system_prompt(base_dir=str(Path(__file__).parent.parent))
        self.audit = AuditService(dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE)
        self.token_service = TokenService()
        self.processor = FailureLogProcessor(token_service=self.token_service)
        self.mcp = MCPService()
        self.client = genai.Client(
            vertexai=True,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=self.prompt_config.location,
        )

    async def solve(self, session_id: str, max_iterations: int = 5) -> RunTaskResponse:
        logger.info(f"Starting Google GenAI SDK solve for session {session_id}")

        # 1. Audit: Session Initialized
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Session {session_id} initialized with backend genai",
            step_type="session_start",
            metadata={"max_iterations": max_iterations, "dataset": config.BQ_DATASET},
        )

        # 2. Stage failure.log into cr-mcp-workspace via cr-mcp-web-gateway
        logger.info("Staging failure.log via cr-mcp-web-gateway into workspace")
        fetch_result = await self.mcp.fetch_web_resource(
            session_id=session_id,
            url=config.AIDEVS_FAILURE_DATA_URL,
            output_path="failure.log",
        )
        logger.info(f"Staged failure.log: {fetch_result}")

        await self.audit.log_event(
            session_id=session_id,
            actor="mcp",
            content=f"Staged failure.log into session workspace: {fetch_result}",
            step_type="data_staged",
        )

        # 3. Read failure.log from workspace into memory
        logger.info("Reading failure.log from workspace into memory")
        raw_content = await self.mcp.read_file(session_id=session_id, file_path="failure.log")

        # 4. In-memory telemetry filtering and condensation
        lines = raw_content.splitlines()
        parsed_events = [e for l in lines if (e := self.processor.parse_line(l)) is not None]
        filtered_events = self.processor.filter_events(parsed_events)
        condensed_payload, token_count = self.processor.condense_events(
            filtered_events, max_tokens=config.SAFE_TOKENS_TARGET
        )
        logger.info(f"GenAI Agent: Baseline condensed telemetry: {token_count} tokens")

        # 5. Autonomous Verification & Remediation Loop
        captured_flag: Optional[str] = None
        iteration_count = 0
        final_condensed_text = condensed_payload

        for iteration in range(1, max_iterations + 1):
            iteration_count = iteration
            logger.info(f"--- GenAI Verification Iteration {iteration}/{max_iterations} (Tokens: {token_count}) ---")

            token_count, is_valid = self.token_service.validate_budget(final_condensed_text, config.MAX_TOKENS_LIMIT)
            if not is_valid:
                final_condensed_text, token_count = self.processor.condense_events(filtered_events, max_tokens=config.SAFE_TOKENS_TARGET)

            verify_payload = {
                "apikey": config.AIDEVS_API_KEY,
                "task": config.TASK_NAME,
                "answer": {"logs": final_condensed_text},
            }

            await self.audit.log_event(
                session_id=session_id,
                actor="agent",
                content=f"Submitting iteration {iteration} to verification endpoint (Tokens: {token_count})",
                step_type="verification_submission",
                metadata={"iteration": iteration, "token_count": token_count},
            )

            response_json = await self.mcp.post_web_resource(
                session_id=session_id,
                url=config.AIDEVS_VERIFY_URL,
                payload=verify_payload,
            )
            logger.info(f"GenAI Verification response (iter {iteration}): {response_json}")

            captured_flag = self.processor.extract_flag(response_json)
            if captured_flag:
                logger.info(f"GenAI Agent SUCCESS! Flag captured: {captured_flag}")
                await self.audit.log_event(
                    session_id=session_id,
                    actor="centrala",
                    content="Verification succeeded with completion flag",
                    step_type="verification_success",
                    flag="[REDACTED_FLAG]",
                    metadata={"iteration": iteration, "response": response_json},
                )
                break

            feedback_msg = response_json.get("message") or response_json.get("feedback") or str(response_json)
            await self.audit.log_event(
                session_id=session_id,
                actor="centrala",
                content=f"Technician feedback on iteration {iteration}: {feedback_msg}",
                step_type="feedback_received",
                metadata={"iteration": iteration, "feedback": feedback_msg},
            )

            missing_components = self.processor.extract_components_from_feedback(feedback_msg)
            if missing_components:
                filtered_events = self.processor.remediate_with_missing_components(
                    raw_log_content=raw_content,
                    current_events=filtered_events,
                    missing_components=missing_components,
                )
                final_condensed_text, token_count = self.processor.condense_events(
                    filtered_events, max_tokens=config.SAFE_TOKENS_TARGET
                )
            else:
                filtered_events = self.processor.filter_events(parsed_events, start_hour=5, end_hour=23)
                final_condensed_text, token_count = self.processor.condense_events(
                    filtered_events, max_tokens=config.SAFE_TOKENS_TARGET
                )

        # 6. Write execution summary to run_notes.txt via workspace
        now_str = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        status_str = "SUCCESS" if captured_flag else "FAILED"
        report_content = (
            f"Task: {config.TASK_NAME} (S02E03)\n"
            f"Backend: genai\n"
            f"Session ID: {session_id}\n"
            f"Timestamp: {now_str}\n"
            f"Token Count: {token_count} / {config.MAX_TOKENS_LIMIT}\n"
            f"Iterations: {iteration_count}\n"
            f"Status: {status_str}\n"
            f"Flag: {captured_flag or 'NOT_CAPTURED'}\n"
        )
        await self.mcp.write_file(session_id=session_id, file_path="run_notes.txt", content=report_content)

        # 7. Final Audit Event
        await self.audit.log_event(
            session_id=session_id,
            actor="agent",
            content=f"Task completed with status {status_str}",
            step_type="final_answer",
            flag="[REDACTED_FLAG]" if captured_flag else None,
            metadata={"status": status_str, "iterations": iteration_count, "tokens": token_count},
        )

        preview_sample = "\n".join(final_condensed_text.splitlines()[:5])
        return RunTaskResponse(
            status="success" if captured_flag else "partial",
            session_id=session_id,
            flag=captured_flag,
            token_count=token_count,
            iterations=iteration_count,
            condensed_logs_sample=preview_sample,
            notes_file="run_notes.txt",
        )
