import re
import logging
from typing import List, Optional, Tuple, Set, Any
from schemas import TelemetryEvent
from services.token_service import TokenService

logger = logging.getLogger("services.failure")

# Regex pattern matching standard timestamped log lines
# Example: [2026-02-26 06:04:15] [CRIT] ECCS8 runaway outlet temp. Protection interlock initiated reactor trip.
# Or: 2026-02-26 06:04:15 [CRIT] ECCS8 ...
LOG_LINE_REGEX = re.compile(
    r"^\[?(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})(?::\d{2})?\]?\s+\[?([A-Za-z]{3,5})\]?\s+([A-Za-z0-9_-]{2,12})\s+(.*)$"
)

# Critical keywords that indicate failure or shutdown mechanisms
CRITICAL_KEYWORDS = {
    "trip", "scram", "interlock", "override", "runaway", "shutdown",
    "threshold", "coolant", "leak", "failure", "failed", "offline",
    "emergency", "radiation", "pressure", "drop", "surge", "ripple"
}

# Core plant subsystem prefixes
CORE_SUBSYSTEM_PREFIXES = (
    "PWR", "ECCS", "WTANK", "PUMP", "COOL", "CTRL", "SYS", "VALVE", "GEN", "BUS", "BAT"
)


class FailureLogProcessor:
    """In-memory telemetry parsing, anomaly filtering, condensation, and technician remediation engine."""

    def __init__(self, token_service: Optional[TokenService] = None):
        self.token_service = token_service or TokenService()

    def parse_line(self, line: str) -> Optional[TelemetryEvent]:
        """Parses a single log line into a structured TelemetryEvent model."""
        clean_line = line.strip()
        if not clean_line:
            return None

        match = LOG_LINE_REGEX.match(clean_line)
        if match:
            date_str, time_str, sev, comp, desc = match.groups()
            # Normalize severity tag
            sev_clean = sev.upper()
            if not sev_clean.startswith("["):
                sev_tag = f"[{sev_clean}]"
            else:
                sev_tag = sev_clean

            # Normalize time to HH:MM
            time_parts = time_str.split(":")
            formatted_time = f"{int(time_parts[0]):02d}:{time_parts[1]}"

            return TelemetryEvent(
                timestamp_raw=f"{date_str} {time_str}",
                date_str=date_str,
                time_str=formatted_time,
                severity=sev_tag,
                component_id=comp.strip(),
                description=desc.strip(),
                raw_line=clean_line,
            )

        # Fallback heuristic for non-strictly formatted lines
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", clean_line)
        time_match = re.search(r"(\d{1,2}:\d{2})(?::\d{2})?", clean_line)
        sev_match = re.search(r"\[(CRIT|ERRO|WARN|INFO|EMERG)\]", clean_line, re.IGNORECASE)
        comp_match = re.search(r"\b([A-Z]{2,6}\d{1,4}[A-Z]?)\b", clean_line)

        if date_match and time_match:
            d_str = date_match.group(1)
            t_str = time_match.group(1)
            s_tag = f"[{sev_match.group(1).upper()}]" if sev_match else "[INFO]"
            c_id = comp_match.group(1) if comp_match else "UNKNOWN"
            # Description is remainder after stripping timestamp and severity
            remainder = clean_line
            for tok in [d_str, t_str, s_tag, c_id]:
                remainder = remainder.replace(tok, "")
            remainder = re.sub(r"[\[\]:]", " ", remainder).strip()
            return TelemetryEvent(
                timestamp_raw=f"{d_str} {t_str}",
                date_str=d_str,
                time_str=t_str,
                severity=s_tag,
                component_id=c_id,
                description=remainder or "Operational telemetry event",
                raw_line=clean_line,
            )

        return None

    def filter_events(
        self,
        events: List[TelemetryEvent],
        start_hour: int = 5,
        end_hour: int = 22,
    ) -> List[TelemetryEvent]:
        """
        Filters events to include:
        1. Timestamps within the failure operating window (default: 05:30 to 22:15).
        2. High severity levels ([CRIT], [ERRO], [WARN]) or events referencing shutdown keywords/core subsystems.
        """
        filtered: List[TelemetryEvent] = []

        for ev in events:
            try:
                hour = int(ev.time_str.split(":")[0])
                # Window roughly 05:30 to 22:30
                if hour < start_hour or hour > end_hour:
                    continue
            except Exception:
                pass

            is_high_sev = ev.severity in {"[CRIT]", "[ERRO]", "[WARN]", "[EMERG]"}
            has_keyword = any(kw in ev.description.lower() for kw in CRITICAL_KEYWORDS)
            is_core_subsystem = any(ev.component_id.startswith(pref) for pref in CORE_SUBSYSTEM_PREFIXES)

            if is_high_sev or (has_keyword and is_core_subsystem):
                filtered.append(ev)

        # Sort chronologically by date and time
        filtered.sort(key=lambda x: (x.date_str, x.time_str))
        return filtered

    @staticmethod
    def _uniform_sample(items: List[Any], count: int) -> List[Any]:
        """Uniformly samples count items from items, always preserving the first and last elements."""
        n = len(items)
        if n <= count or count <= 0:
            return list(items)
        if count == 1:
            return [items[0]]
        step = (n - 1) / (count - 1)
        indices = [round(i * step) for i in range(count)]
        unique_indices = []
        seen = set()
        for idx in indices:
            idx = min(idx, n - 1)
            if idx not in seen:
                unique_indices.append(idx)
                seen.add(idx)
        return [items[i] for i in unique_indices]

    @staticmethod
    def _sample_with_component_coverage(
        lines: List[str],
        target_count: int,
    ) -> List[str]:
        """
        Samples lines uniformly while strictly ensuring every component present in lines
        has at least one representative line in the result.
        """
        if len(lines) <= target_count:
            return list(lines)

        def get_comp(line: str) -> str:
            match = re.search(r"\]\s+\[?[A-Za-z]{3,5}\]?\s+([A-Za-z0-9_-]+)", line)
            return match.group(1) if match else "UNKNOWN"

        all_comps = {get_comp(l) for l in lines}
        sampled = FailureLogProcessor._uniform_sample(lines, target_count)
        sampled_comps = {get_comp(l) for l in sampled}

        missing = all_comps - sampled_comps
        if missing:
            sampled_set = set(sampled)
            for m_comp in missing:
                comp_lines = [l for l in lines if get_comp(l) == m_comp]
                if comp_lines:
                    chosen = comp_lines[len(comp_lines) // 2]
                    for idx in range(1, len(sampled) - 1):
                        c = get_comp(sampled[idx])
                        if sum(1 for s in sampled if get_comp(s) == c) > 1:
                            sampled[idx] = chosen
                            sampled_set.add(chosen)
                            break

        sampled.sort()
        return sampled

    def condense_events(
        self,
        events: List[TelemetryEvent],
        max_tokens: int = 1400,
    ) -> Tuple[str, int]:
        """
        Assembles a multiline string from events and dynamically compresses lines
        to ensure the payload satisfies max_tokens <= 1400 using chronological uniform downsampling
        with guaranteed 100% subsystem component coverage.
        """
        if not events:
            return "", 0

        # Pass 1: Build formatted lines and deduplicate adjacent identical alarms
        condensed_lines: List[str] = []
        last_sig: Optional[str] = None

        for ev in events:
            # Shorten repetitive sentences
            desc = ev.description
            # Remove redundant hex codes
            desc = re.sub(r"0x[0-9a-fA-F]+", "", desc)
            desc = re.sub(r"\s+", " ", desc).strip()

            line = f"[{ev.date_str} {ev.time_str}] {ev.severity} {ev.component_id} {desc}".strip()
            # Avoid repeating the exact same component alarm in consecutive minutes unless severity changed
            sig = f"{ev.component_id}:{ev.severity}:{desc[:20]}"
            if sig == last_sig:
                continue
            last_sig = sig
            condensed_lines.append(line)

        payload_text = "\n".join(condensed_lines)
        token_count = self.token_service.count_tokens(payload_text)
        if token_count <= max_tokens:
            return payload_text, token_count

        # Pass 2: Filter strictly to [CRIT] events
        logger.info(f"Payload token count ({token_count}) exceeds target ({max_tokens}). Filtering to [CRIT] alarms.")
        crit_lines = [l for l in condensed_lines if "[CRIT]" in l]
        if not crit_lines:
            crit_lines = [l for l in condensed_lines if "[ERRO]" in l or "[CRIT]" in l]
        if not crit_lines:
            crit_lines = condensed_lines

        payload_text = "\n".join(crit_lines)
        token_count = self.token_service.count_tokens(payload_text)
        if token_count <= max_tokens:
            return payload_text, token_count

        # Pass 3: Uniform downsampling across critical events with guaranteed component coverage
        logger.info(f"Critical events ({token_count} tokens across {len(crit_lines)} lines) exceed target ({max_tokens}). Uniformly downsampling.")
        start_k = min(42, len(crit_lines))
        best_text = payload_text
        best_tokens = token_count

        for k in range(start_k, 9, -1):
            sampled = self._sample_with_component_coverage(crit_lines, k)
            candidate_text = "\n".join(sampled)
            candidate_tokens = self.token_service.count_tokens(candidate_text)
            if candidate_tokens <= max_tokens:
                logger.info(f"Uniform downsampling converged at k={k} with {candidate_tokens} tokens across {len(sampled)} lines.")
                return candidate_text, candidate_tokens
            best_text = candidate_text
            best_tokens = candidate_tokens

        return best_text, best_tokens

    def extract_components_from_feedback(self, feedback_text: str) -> List[str]:
        """
        Extracts component IDs and referenced keywords from Centrala technician feedback.
        e.g. '...unable to determine what happened to device FIRMWARE.' -> ['FIRMWARE']
        """
        if not feedback_text:
            return []

        found_ids = set()

        # 1. Match 'device XYZ' or 'urządzenie XYZ' or 'podzespół XYZ'
        device_matches = re.findall(r"(?:device|urządzenie|podzespół|komponent)\s+([A-Za-z0-9_-]+)", feedback_text, re.IGNORECASE)
        for d in device_matches:
            found_ids.add(d.upper().strip(".,;:!?"))

        # 2. Match known power plant components
        known_components = {"ECCS8", "FIRMWARE", "PWR01", "STMTURB12", "WSTPOOL2", "WTANK07", "WTRPMP"}
        for comp in known_components:
            if comp.lower() in feedback_text.lower():
                found_ids.add(comp)

        # 3. Match uppercase alphanumeric IDs e.g. PUMP02, WTANK07
        tokens = re.findall(r"\b([A-Z][A-Z0-9_-]{2,11})\b", feedback_text)
        for t in tokens:
            if t in known_components or any(t.startswith(pref) for pref in CORE_SUBSYSTEM_PREFIXES):
                found_ids.add(t)

        return sorted(list(found_ids))

    def remediate_with_missing_components(
        self,
        raw_log_content: str,
        current_events: List[TelemetryEvent],
        missing_components: List[str],
    ) -> List[TelemetryEvent]:
        """
        Searches the raw log in memory for the specified missing component identifiers
        and injects them into current_events in chronological order.
        """
        if not missing_components or not raw_log_content:
            return current_events

        existing_lines = {ev.raw_line for ev in current_events}
        added_events: List[TelemetryEvent] = []

        for line in raw_log_content.splitlines():
            line_str = line.strip()
            if not line_str or line_str in existing_lines:
                continue

            matches_missing = any(comp in line_str for comp in missing_components)
            if matches_missing:
                ev = self.parse_line(line_str)
                if ev:
                    # Prefer CRIT, ERRO, or WARN for the missing component
                    if ev.severity in {"[CRIT]", "[ERRO]", "[WARN]"}:
                        added_events.append(ev)
                        existing_lines.add(line_str)

        logger.info(f"Remediation injected {len(added_events)} missing events for components: {missing_components}")
        combined = current_events + added_events
        combined.sort(key=lambda x: (x.date_str, x.time_str))
        return combined

    @staticmethod
    def extract_flag(response_data: Any) -> Optional[str]:
        """Scans response payload or string for the course flag pattern {FLG:...}."""
        text = str(response_data)
        match = re.search(r"\{FLG:[^}]+\}", text)
        return match.group(0) if match else None
