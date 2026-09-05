import os
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
from langchain.agents import create_agent
from af_aidevs.clients.mcp import get_all_mcp_tools
from af_aidevs.utils.prompts import load_system_prompt
import config
from schemas import (
    RunTaskResponse,
    CountTokensInput,
    CountTokensResponse,
    VerifySolutionInput,
    VerifySolutionResponse,
)
from services.audit_service import AuditService, BigQueryCallbackHandler
from services.token_service import TokenService
from services.failure_service import FailureLogProcessor
from services.mcp_service import MCPService

logger = logging.getLogger("agents.langchain")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


class LangChainFailureAgent:
    """LangChain 1.2.15 implementation with real-time BigQuery auditing and zero-trust MCP isolation."""

    def __init__(self):
        self.prompt_config = load_system_prompt(base_dir=str(Path(__file__).parent.parent))
        self.audit = AuditService(dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE)
        self.token_service = TokenService()
        self.processor = FailureLogProcessor(token_service=self.token_service)
        self.mcp = MCPService()
        os.environ["LANGSMITH_PROJECT"] = config.LANGSMITH_PROJECT

        self.llm = ChatGoogleGenerativeAI(
            model=self.prompt_config.model,
            temperature=self.prompt_config.temperature,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=self.prompt_config.location,
            vertexai=True,
        )

    def _create_specialist_tools(self, session_id: str, raw_cache: Dict[str, str]):
        """Creates specialist tools for token validation and log condensation."""
        token_svc = self.token_service
        proc = self.processor

        @tool(args_schema=CountTokensInput)
        def count_candidate_tokens(reasoning: str, text: str) -> str:
            """Calculates exact token count of candidate condensed logs using Vertex AI to verify it does not exceed 1500 tokens."""
            tokens = token_svc.count_tokens(text)
            is_valid = tokens <= config.MAX_TOKENS_LIMIT
            resp = CountTokensResponse(
                token_count=tokens,
                is_valid=is_valid,
                max_allowed=config.MAX_TOKENS_LIMIT,
                safe_target=config.SAFE_TOKENS_TARGET,
                hint="Token count within safe limits. Ready to submit." if is_valid else f"Token count {tokens} exceeds 1500! Must compress further.",
            )
            return resp.model_dump_json()

        @tool
        def condense_log_telemetry(
            reasoning: str = "Parsing and filtering failure.log from workspace memory",
            file_name: str = "failure.log",
        ) -> str:
            """Processes the staged failure log in memory to extract high-severity anomalies, trips, and core subsystems between 06:00 and 22:00, condensed to <= 1400 tokens."""
            content = raw_cache.get(file_name)
            if not content:
                return json.dumps({"error": f"File '{file_name}' not yet loaded in memory. Call read_file first."})

            lines = content.splitlines()
            events = [proc.parse_line(l) for l in lines]
            valid_events = [e for e in events if e is not None]
            filtered = proc.filter_events(valid_events)
            condensed_text, token_count = proc.condense_events(filtered, max_tokens=config.SAFE_TOKENS_TARGET)

            return json.dumps({
                "status": "success",
                "total_events_identified": len(filtered),
                "token_count": token_count,
                "is_within_limit": token_count <= config.MAX_TOKENS_LIMIT,
                "condensed_logs": condensed_text,
                "instruction": "Verify the token count with count_candidate_tokens or submit directly via post_web_resource to $AIDEVS_API_VERIFY.",
            })

        return [count_candidate_tokens, condense_log_telemetry]

    async def solve(self, session_id: str, max_iterations: int = 5) -> RunTaskResponse:
        logger.info(f"Starting LangChain solve for session {session_id}")
        raw_log_cache: Dict[str, str] = {}

        # 1. Audit: Session Initialized
        await self.audit.log_event(
            session_id=session_id,
            actor="system",
            content=f"Session {session_id} initialized with backend langchain",
            step_type="session_start",
            metadata={"max_iterations": max_iterations, "dataset": config.BQ_DATASET},
        )

        # 2. Stage failure.log into cr-mcp-workspace via cr-mcp-web-gateway
        logger.info(f"Staging raw failure.log via cr-mcp-web-gateway into cr-mcp-workspace")
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
        raw_log_cache["failure.log"] = raw_content
        logger.info(f"Read failure.log into memory (length: {len(raw_content)} chars)")

        # 4. Perform in-memory baseline telemetry filtering and compression
        lines = raw_content.splitlines()
        parsed_events = [e for l in lines if (e := self.processor.parse_line(l)) is not None]
        filtered_events = self.processor.filter_events(parsed_events)
        condensed_payload, token_count = self.processor.condense_events(
            filtered_events, max_tokens=config.SAFE_TOKENS_TARGET
        )
        logger.info(f"Initial condensed telemetry generated: {token_count} tokens across {len(condensed_payload.splitlines())} lines")

        # 5. Autonomous Verification & Technician Remediation Loop
        captured_flag: Optional[str] = None
        iteration_count = 0
        final_condensed_text = condensed_payload

        for iteration in range(1, max_iterations + 1):
            iteration_count = iteration
            logger.info(f"--- Verification Iteration {iteration}/{max_iterations} (Tokens: {token_count}) ---")

            # Validate token budget
            token_count, is_valid = self.token_service.validate_budget(final_condensed_text, config.MAX_TOKENS_LIMIT)
            if not is_valid:
                logger.warning(f"Tokens ({token_count}) exceed ceiling! Compressing to safe target.")
                final_condensed_text, token_count = self.processor.condense_events(filtered_events, max_tokens=config.SAFE_TOKENS_TARGET)

            # Submit via cr-mcp-web-gateway to $AIDEVS_API_VERIFY
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
            logger.info(f"Verification response (iter {iteration}): {response_json}")

            # Check for completion flag
            captured_flag = self.processor.extract_flag(response_json)
            if captured_flag:
                logger.info(f"SUCCESS! Flag captured on iteration {iteration}")
                await self.audit.log_event(
                    session_id=session_id,
                    actor="centrala",
                    content="Verification succeeded with completion flag",
                    step_type="verification_success",
                    flag="[REDACTED_FLAG]",
                    metadata={"iteration": iteration, "response": response_json},
                )
                break

            # Handle technician feedback
            feedback_msg = response_json.get("message") or response_json.get("feedback") or str(response_json)
            logger.info(f"Technician feedback received: {feedback_msg}")

            await self.audit.log_event(
                session_id=session_id,
                actor="centrala",
                content=f"Technician feedback on iteration {iteration}: {feedback_msg}",
                step_type="feedback_received",
                metadata={"iteration": iteration, "feedback": feedback_msg},
            )

            # Extract missing components and remediate in memory
            missing_components = self.processor.extract_components_from_feedback(feedback_msg)
            logger.info(f"Identified missing components: {missing_components}")

            if missing_components:
                filtered_events = self.processor.remediate_with_missing_components(
                    raw_log_content=raw_content,
                    current_events=filtered_events,
                    missing_components=missing_components,
                )
                final_condensed_text, token_count = self.processor.condense_events(
                    filtered_events, max_tokens=config.SAFE_TOKENS_TARGET
                )
                logger.info(f"Re-synthesized condensed telemetry: {token_count} tokens")
            else:
                logger.warning("No specific components parsed from feedback. Re-evaluating severity filters.")
                # Broaden to include more warnings
                filtered_events = self.processor.filter_events(parsed_events, start_hour=5, end_hour=23)
                final_condensed_text, token_count = self.processor.condense_events(
                    filtered_events, max_tokens=config.SAFE_TOKENS_TARGET
                )

        # 6. Save execution report to run_notes.txt via cr-mcp-workspace
        now_str = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        status_str = "SUCCESS" if captured_flag else "FAILED"
        report_content = (
            f"Task: {config.TASK_NAME} (S02E03)\n"
            f"Backend: langchain\n"
            f"Session ID: {session_id}\n"
            f"Timestamp: {now_str}\n"
            f"Token Count: {token_count} / {config.MAX_TOKENS_LIMIT}\n"
            f"Iterations: {iteration_count}\n"
            f"Status: {status_str}\n"
            f"Flag: {captured_flag or 'NOT_CAPTURED'}\n"
        )
        await self.mcp.write_file(session_id=session_id, file_path="run_notes.txt", content=report_content)
        logger.info(f"Saved execution report to run_notes.txt in workspace")

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
