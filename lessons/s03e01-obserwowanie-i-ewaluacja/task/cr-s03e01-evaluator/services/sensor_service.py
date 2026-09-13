import io
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Set, Tuple
import zipfile

from config import (
    ALLOWED_SENSOR_TYPES,
    FIELD_TO_METRIC,
    MAX_VALID_TIMESTAMP,
    METRIC_TO_FIELD,
    MIN_VALID_TIMESTAMP,
    SENSOR_BOUNDS,
)
from schemas import SensorReading

logger = logging.getLogger("services.sensor")


class SensorService:
    """Processes sensor zip archive in memory and performs deterministic telemetry audits."""

    @staticmethod
    def extract_file_id(file_name: str) -> str:
        """Extracts standard file identifier (e.g. '0001' from '0001.json' or 'data/0001.json')."""
        return Path(file_name).stem

    @classmethod
    def normalize_and_validate_note(cls, raw_note: str) -> Tuple[bool, str, str]:
        """Normalizes operator note and validates against degenerate/dummy patterns.

        Returns:
            (is_anomaly, reason, normalized_note)
        """
        if not isinstance(raw_note, str):
            return True, "Operator note is not a string", ""

        cleaned = re.sub(r"\s+", " ", raw_note).strip()
        if not cleaned:
            return True, "Operator note is empty or whitespace-only", ""

        if len(cleaned) < 3:
            return True, f"Operator note too short: '{cleaned}'", cleaned

        # Check for degenerate repetition (e.g. 10x 'a' or single repeating character)
        chars_only = re.sub(r"[\s\W_]+", "", cleaned).lower()
        if len(chars_only) >= 3 and len(set(chars_only)) <= 1:
            return True, f"Operator note contains degenerate repeating characters: '{cleaned}'", cleaned

        return False, "OK", cleaned

    @classmethod
    def audit_single_record(cls, reading: SensorReading) -> Tuple[bool, str]:
        """Checks if a sensor reading violates timestamp, type, physical limits or inactive channel rules.

        Returns (is_anomaly, reason).
        """
        # 1. Timestamp sanity check [2026-01-01, 2026-07-01]
        if not (MIN_VALID_TIMESTAMP <= reading.timestamp <= MAX_VALID_TIMESTAMP):
            return (
                True,
                f"Timestamp {reading.timestamp} outside valid range [2026-01-01, 2026-07-01]",
            )

        # 2. Strict sensor type validation against allowed firmware types
        raw_types = [t.strip().lower() for t in reading.sensor_type.split("/") if t.strip()]
        if not raw_types:
            return True, "Empty or missing sensor_type"

        for t in raw_types:
            if t not in ALLOWED_SENSOR_TYPES:
                return True, f"Unknown/malformed sensor_type component: '{t}'"

        active_metrics = set(raw_types)

        # 3. Operator note normalization and validation
        is_bad_note, note_reason, norm_note = cls.normalize_and_validate_note(reading.operator_notes)
        if is_bad_note:
            return True, f"Invalid operator note: {note_reason}"

        # 4. Physical metrics and ghost readings validation
        for metric, (min_val, max_val) in SENSOR_BOUNDS.items():
            field_name = METRIC_TO_FIELD[metric]
            val = getattr(reading, field_name, 0.0)

            if metric in active_metrics:
                # Active sensor reading must fall within physical boundaries
                if val < min_val or val > max_val:
                    return (
                        True,
                        f"Active metric '{metric}' value {val} out of bounds [{min_val}, {max_val}]",
                    )
            else:
                # Inactive sensor channel must strictly equal 0
                if val != 0 and abs(val) > 1e-6:
                    return (
                        True,
                        f"Inactive metric '{metric}' has ghost reading {val} (expected 0)",
                    )

        return (False, "OK")

    @classmethod
    def process_zip_archive(
        cls, zip_bytes: bytes
    ) -> Tuple[int, List[str], Dict[str, List[str]], List[Dict[str, Any]]]:
        """Streams and validates JSON files inside the ZIP archive in memory.

        Returns:
            total_scanned: Total number of JSON files evaluated
            physical_anomaly_file_ids: List of file IDs failing deterministic checks
            note_to_clean_files: Mapping of unique operator note string to list of file IDs
            clean_records: Full records of healthy measurements needing AI note classification
        """
        physical_anomalies: List[str] = []
        note_to_clean_files: Dict[str, List[str]] = {}
        clean_records: List[Dict[str, Any]] = []
        total_scanned = 0

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            namelist = sorted([n for n in zf.namelist() if n.endswith(".json") and not n.startswith("__MACOSX")])
            total_scanned = len(namelist)
            logger.info(f"Loaded {total_scanned} JSON records from ZIP archive.")

            for fname in namelist:
                file_id = cls.extract_file_id(fname)
                raw_json = zf.read(fname).decode("utf-8")
                try:
                    data = json.loads(raw_json)
                    reading = SensorReading(**data)
                except Exception as e:
                    logger.warning(f"Malformed JSON / strict schema error in file {fname}: {e}")
                    physical_anomalies.append(file_id)
                    continue

                is_anomaly, reason = cls.audit_single_record(reading)
                if is_anomaly:
                    physical_anomalies.append(file_id)
                else:
                    norm_note = re.sub(r"\s+", " ", reading.operator_notes).strip()
                    note_to_clean_files.setdefault(norm_note, []).append(file_id)
                    clean_records.append({
                        "file_id": file_id,
                        "sensor_type": reading.sensor_type,
                        "timestamp": reading.timestamp,
                        "temperature_K": reading.temperature_K,
                        "pressure_bar": reading.pressure_bar,
                        "water_level_meters": reading.water_level_meters,
                        "voltage_supply_v": reading.voltage_supply_v,
                        "humidity_percent": reading.humidity_percent,
                        "operator_notes": norm_note,
                    })

        logger.info(
            f"Audit complete: {len(physical_anomalies)} physical/deterministic anomalies found. "
            f"{len(clean_records)} clean records ({len(note_to_clean_files)} unique notes) ready for AI classification."
        )
        return total_scanned, physical_anomalies, note_to_clean_files, clean_records
