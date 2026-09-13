import base64
from datetime import datetime
import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from agents.base import BaseEvaluator
import config
from schemas import RunTaskResponse
from services.audit_service import AuditService, generate_session_id
from services.mcp_service import MCPService
from services.note_classifier import NoteClassifier
from services.sensor_service import SensorService

logger = logging.getLogger("agents.pipeline")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


class EvaluatorPipeline(BaseEvaluator):
    """Deterministic, contract-first evaluation pipeline with LLM-augmented note classification."""

    def __init__(self, backend: str = "langchain"):
        self.backend = backend.strip().lower()
        self.audit = AuditService(dataset_id=config.BQ_DATASET, table_id=config.BQ_TABLE)
        self.mcp = MCPService()
        self.classifier = NoteClassifier(backend=self.backend)

    async def run(self, session_id: Optional[str] = None) -> RunTaskResponse:
        session_id = session_id or generate_session_id(self.backend)
        logger.info(f"Starting S03E01 Evaluation Pipeline for session: {session_id} (backend: {self.backend})")

        await self.audit.log_event(
            session_id=session_id,
            actor="pipeline",
            content=f"Starting evaluation pipeline with backend: {self.backend}",
            step_type="general",
            metadata={"backend": self.backend, "model": config.GEMINI_MODEL},
        )

        # Step 1: Download sensors.zip through cr-mcp-web-gateway
        logger.info(f"Downloading telemetry archive from $AIDEVS_SENSORS_DATA_URL...")
        fetch_res = await self.mcp.fetch_web_resource(
            session_id=session_id,
            url=config.AIDEVS_SENSORS_DATA_URL,
            output_path="sensors.zip",
        )
        logger.info(f"Gateway download result: {fetch_res}")

        # Step 2: Read binary sensors.zip through cr-mcp-workspace
        logger.info("Reading binary sensors.zip from session workspace...")
        read_res = await self.mcp.read_binary_file(
            session_id=session_id,
            file_path="sensors.zip",
            reasoning="Ingesting sensor telemetry archive for industrial QA audit",
        )

        base64_content = read_res.get("content_base64")
        if not base64_content:
            err_msg = f"Failed to retrieve base64 content from workspace: {read_res}"
            logger.error(err_msg)
            await self.audit.log_event(
                session_id=session_id,
                actor="pipeline",
                content=err_msg,
                step_type="tool_error",
                metadata=read_res,
            )
            raise RuntimeError(err_msg)

        zip_bytes = base64.b64decode(base64_content)
        expected_sha = read_res.get("sha256")
        actual_sha = hashlib.sha256(zip_bytes).hexdigest()
        if expected_sha and actual_sha != expected_sha:
            logger.warning(f"SHA-256 mismatch! Expected {expected_sha}, got {actual_sha}")

        # Step 3: Deterministic Physical Audit via SensorService
        logger.info("Decompressing archive and executing physical sensor audit...")
        total_scanned, physical_anomalies, note_to_clean_files, clean_records = (
            SensorService.process_zip_archive(zip_bytes)
        )

        await self.audit.log_event(
            session_id=session_id,
            actor="pipeline",
            content=(
                f"Physical audit completed: {total_scanned} scanned, "
                f"{len(physical_anomalies)} physical anomalies, "
                f"{len(clean_records)} clean records ({len(note_to_clean_files)} unique notes) ready for AI classification."
            ),
            step_type="tool_result",
            metadata={
                "total_scanned": total_scanned,
                "physical_anomalies_count": len(physical_anomalies),
                "clean_records_count": len(clean_records),
                "unique_notes_count": len(note_to_clean_files),
            },
        )

        # Step 4: Staging records to workspace as CSV and JSON (for Artur's inspection before LLM calls)
        logger.info(
            f"Staging {len(clean_records)} candidate records and {len(note_to_clean_files)} "
            f"unique notes to session workspace..."
        )

        # Build CSV of all clean records
        csv_lines = [
            "file_id,sensor_type,timestamp,temperature_K,pressure_bar,water_level_meters,voltage_supply_v,humidity_percent,operator_notes"
        ]
        for r in clean_records:
            escaped_notes = r["operator_notes"].replace('"', '""')
            csv_lines.append(
                f'{r["file_id"]},{r["sensor_type"]},{r["timestamp"]},{r["temperature_K"]},'
                f'{r["pressure_bar"]},{r["water_level_meters"]},{r["voltage_supply_v"]},'
                f'{r["humidity_percent"]},"{escaped_notes}"'
            )
        csv_content = "\n".join(csv_lines)

        # Build JSON of unique notes and mapped file IDs
        notes_summary = [
            {
                "note": note,
                "occurrences": len(fids),
                "file_ids": fids,
            }
            for note, fids in sorted(note_to_clean_files.items(), key=lambda x: -len(x[1]))
        ]
        json_content = json.dumps(notes_summary, indent=2, ensure_ascii=False)

        await self.mcp.write_file(
            session_id=session_id,
            file_path="records_to_classify.csv",
            content=csv_content,
            reasoning="Staging clean telemetry records requiring AI operator note classification",
        )
        await self.mcp.write_file(
            session_id=session_id,
            file_path="notes_to_classify.json",
            content=json_content,
            reasoning="Staging unique operator notes and mapped file IDs for AI classification",
        )

        # Also write local copies if running locally or in development
        try:
            local_csv_path = Path("records_to_classify.csv")
            local_json_path = Path("notes_to_classify.json")
            local_csv_path.write_text(csv_content, encoding="utf-8")
            local_json_path.write_text(json_content, encoding="utf-8")
            logger.info(f"Local copies written to {local_csv_path} and {local_json_path}")
        except Exception as e:
            logger.warning(f"Could not write local copies: {e}")

        # Step 5: Semantic Operator Note Classification (Single-Prompt High-Efficiency Batch)
        unique_notes = [entry["note"] for entry in notes_summary]
        logger.info(
            f"Classifying {len(unique_notes)} unique notes via {config.GEMINI_MODEL} (backend: {self.backend})..."
        )
        anomaly_indices = await self.classifier.classify_all_notes(unique_notes)
        logger.info(f"Classifier returned {len(anomaly_indices)} anomaly note indices: {anomaly_indices}")

        operator_false_positives: List[str] = []
        flagged_notes_details = []
        for idx in anomaly_indices:
            if 0 <= idx < len(notes_summary):
                entry = notes_summary[idx]
                fids = entry["file_ids"]
                operator_false_positives.extend(fids)
                flagged_notes_details.append({
                    "index": idx,
                    "note": entry["note"],
                    "affected_files": fids,
                })

        logger.info(
            f"Operator note audit completed: {len(flagged_notes_details)} anomaly notes flagged, "
            f"impacting {len(operator_false_positives)} healthy sensor files."
        )

        # Save AI classification outcome artifact in MCP workspace
        classified_anomalies_content = json.dumps({
            "total_unique_notes": len(unique_notes),
            "flagged_notes_count": len(flagged_notes_details),
            "total_affected_files": len(operator_false_positives),
            "flagged_notes": flagged_notes_details,
        }, indent=2, ensure_ascii=False)
        await self.mcp.write_file(
            session_id=session_id,
            file_path="classified_anomalies.json",
            content=classified_anomalies_content,
            reasoning="Saving AI operator note classification outcome artifact",
        )

        await self.audit.log_event(
            session_id=session_id,
            actor="pipeline",
            content=(
                f"Operator note audit completed: {len(operator_false_positives)} "
                f"operator false positives identified across {len(flagged_notes_details)} notes."
            ),
            step_type="thought",
            metadata={
                "operator_false_positives_count": len(operator_false_positives),
                "unique_notes_evaluated": len(unique_notes),
                "flagged_notes": flagged_notes_details,
            },
        )

        # Step 6: Consolidate all anomalies and prepare submission
        all_anomalies = set(physical_anomalies + operator_false_positives)
        recheck_list = sorted(list(all_anomalies))
        logger.info(
            f"Consolidated anomalies: {len(recheck_list)} files marked for recheck "
            f"({len(physical_anomalies)} physical + {len(operator_false_positives)} operator false alarms)."
        )

        # Save final consolidated recheck list artifact in MCP workspace
        recheck_content = json.dumps({
            "total_anomalies": len(recheck_list),
            "physical_anomalies_count": len(physical_anomalies),
            "operator_false_positives_count": len(operator_false_positives),
            "recheck": recheck_list,
        }, indent=2)
        await self.mcp.write_file(
            session_id=session_id,
            file_path="recheck_anomalies.json",
            content=recheck_content,
            reasoning="Saving consolidated recheck anomaly file list artifact",
        )

        # Step 7: Dispatch /verify submission via cr-mcp-web-gateway
        verify_payload = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": {
                "recheck": recheck_list,
            },
        }

        logger.info(f"Submitting {len(recheck_list)} recheck IDs to Centrala /verify...")
        verify_response = await self.mcp.post_web_resource(
            session_id=session_id,
            url=config.AIDEVS_VERIFY_URL,
            payload=verify_payload,
        )
        logger.info(f"Centrala /verify response: {verify_response}")

        # Extract flag if present
        resp_json_str = json.dumps(verify_response)
        flag_match = re.search(r"(\{[Ff][Ll][Gg]:[^\}]+\})", resp_json_str)
        flag = flag_match.group(1) if flag_match else verify_response.get("flag")

        # Step 8: Write run_notes.txt execution summary into session workspace
        now_str = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S")
        run_notes = (
            f"=== S03E01 Evaluation Run Notes ===\n"
            f"Timestamp (Europe/Zurich): {now_str}\n"
            f"Session ID: {session_id}\n"
            f"Backend: {self.backend}\n"
            f"Model: {config.GEMINI_MODEL}\n"
            f"Total Records Scanned: {total_scanned}\n"
            f"Physical Sensor Anomalies: {len(physical_anomalies)}\n"
            f"Operator False Positives: {len(operator_false_positives)}\n"
            f"Total Anomalies Submitted: {len(recheck_list)}\n"
            f"Verification Result: {verify_response.get('message') or verify_response.get('code', 'OK')}\n"
            f"Flag: {flag or '[NO_FLAG_RETURNED]'}\n"
        )
        await self.mcp.write_file(
            session_id=session_id,
            file_path="run_notes.txt",
            content=run_notes,
            reasoning="Saving S03E01 evaluation outcome and verification report",
        )

        # Step 9: Log final audit event to BigQuery
        await self.audit.log_event(
            session_id=session_id,
            actor="pipeline",
            content=f"Pipeline complete. Flag: {flag or 'None'}",
            step_type="final_answer",
            metadata={
                "total_scanned": total_scanned,
                "physical_anomalies_count": len(physical_anomalies),
                "operator_false_positives_count": len(operator_false_positives),
                "recheck_count": len(recheck_list),
                "flagged_notes": flagged_notes_details,
                "verify_response": verify_response,
            },
            flag=flag,
        )

        status = "success" if (flag or verify_response.get("code") == 0) else "completed"
        return RunTaskResponse(
            status=status,
            session_id=session_id,
            task=config.TASK_NAME,
            total_scanned=total_scanned,
            anomalies_found=len(recheck_list),
            recheck=recheck_list,
            verification_response=verify_response,
            flag=flag,
            hint="Telemetry audit completed. Summary saved to run_notes.txt and logged to BigQuery.",
        )
