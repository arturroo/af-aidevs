"""Service for polling OKO frequency scanner, parsing jammed telemetry, and disarming radar."""

import hashlib
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from config import config
from schemas import RadarTelemetryExtraction
from services.gateway_service import GatewayService
from services.model_armor_service import ModelArmorService

logger = logging.getLogger("services.scanner")

SCANNER_SYSTEM_PROMPT = """You are a signals intelligence telemetry decoder for an autonomous rocket system.
The rocket's scanner received a radar detection packet from the hostile OKO automated tracking network.
Active jamming systems have distorted the data — keys may be malformed, quotes missing, or junk noise tokens injected.

Your objective:
1. Determine if the transmission indicates the sector is clear ('It's clear!') or if the rocket is locked on by an OKO radar.
2. If locked on, extract:
   - 'frequency': The numeric radar tracking frequency (integer or float).
   - 'detection_code': The alphanumeric detection code string required for cryptographic disarming.
3. Provide your rationale in 'reasoning'.
"""


def compute_disarm_hash(detection_code: str) -> str:
    """Calculates SHA-1 hash of detectionCode + 'disarm'."""
    clean_code = detection_code.strip()
    to_hash = f"{clean_code}disarm".encode()
    return hashlib.sha1(to_hash).hexdigest()


def extract_regex_fallback(raw_text: str) -> tuple[float | None, str | None]:
    """Heuristic regex token recovery for jammed payloads."""
    freq: float | None = None
    code: str | None = None

    # Match frequency: e.g. "frequency": 123 or frequency: 123.45
    freq_match = re.search(
        r"""["']?frequency["']?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)""",
        raw_text,
        re.IGNORECASE,
    )
    if freq_match:
        try:
            val = float(freq_match.group(1))
            freq = int(val) if val.is_integer() else val
        except ValueError:
            pass

    # Match detectionCode: e.g. "detectionCode": "abc123def" or detectionCode: abc123def
    code_match = re.search(
        r"""["']?detectionCode["']?\s*[:=]\s*["']?([a-zA-Z0-9_\-]+)["']?""",
        raw_text,
        re.IGNORECASE,
    )
    if code_match:
        code = code_match.group(1).strip()

    return freq, code


class ScannerService:
    """Handles radar lock detection, distorted telemetry recovery, and cryptographic disarming."""

    def __init__(
        self,
        gateway: GatewayService | None = None,
        model_armor: ModelArmorService | None = None,
        model_name: str | None = None,
        thinking_level: str | None = None,
    ) -> None:
        self.gateway = gateway or GatewayService()
        self.model_armor = model_armor or ModelArmorService()
        self.model_name = model_name or config.GEMINI_MODEL
        self.thinking_level = thinking_level or config.THINKING_LEVEL

    def _get_llm(self) -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=self.model_name,
            temperature=0.1,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=config.GOOGLE_CLOUD_LOCATION,
            vertexai=True,
            thinking_level=self.thinking_level,
        )

    async def check_airspace(self, api_key: str) -> RadarTelemetryExtraction:
        """Polls frequency scanner and parses telemetry."""
        raw_text = await self.gateway.get_scanner_status(api_key)
        raw_clean = raw_text.strip()

        # Quick heuristic check for obvious clear variations (e.g. "It's clear!", "Its cleeeeeeeear", "clear")
        clean_normalized = re.sub(r"\s+", " ", raw_clean.lower()).strip()
        is_clear_signal = (
            bool(re.search(r"it'?s\s+cle+ar", clean_normalized))
            or bool(re.search(r"\bcle+ar\b", clean_normalized))
            or (
                "clear" in clean_normalized
                and "frequency" not in clean_normalized
                and "detectioncode" not in clean_normalized
                and "detection_code" not in clean_normalized
            )
        )
        if is_clear_signal:
            logger.info(f"Radar scan: Airspace is CLEAR ({raw_clean}).")
            return RadarTelemetryExtraction(
                is_clear=True,
                frequency=None,
                detection_code=None,
                reasoning=f"Scanner reported airspace is clear: '{raw_clean}'",
            )

        logger.info(
            f"Radar scan: Analyzing potentially jammed or locked telemetry: {raw_clean[:180]}"
        )

        # Sanitize against prompt injection
        sanitized_text = await self.model_armor.sanitize_payload(
            raw_clean, context="frequency_scanner"
        )

        # Parse jammed telemetry using Gemini 3.5 Flash-Lite structured output
        try:
            llm = self._get_llm()
            structured_llm = llm.with_structured_output(RadarTelemetryExtraction)
            messages = [
                SystemMessage(content=SCANNER_SYSTEM_PROMPT),
                HumanMessage(
                    content=f"Decode this distorted radar scanner payload:\n\n{sanitized_text}"
                ),
            ]
            extraction: RadarTelemetryExtraction = await structured_llm.ainvoke(
                messages
            )
            if extraction.is_clear:
                logger.info(
                    f"Radar scan: Airspace confirmed CLEAR by LLM ({raw_clean[:100]}). Reasoning: {extraction.reasoning}"
                )
                return extraction
            if extraction.detection_code and extraction.frequency is not None:
                logger.warning(
                    f"Radar scan: Active OKO radar lock confirmed by LLM! Freq={extraction.frequency}, Code={extraction.detection_code}"
                )
                return extraction
        except Exception as exc:
            logger.warning(
                f"LLM extraction failed on jammed scanner payload ({exc}). Invoking regex fallback."
            )

        # Deterministic fallback via regex
        freq_fallback, code_fallback = extract_regex_fallback(sanitized_text)
        if code_fallback and freq_fallback is not None:
            return RadarTelemetryExtraction(
                is_clear=False,
                frequency=freq_fallback,
                detection_code=code_fallback,
                reasoning=f"Regex fallback successfully extracted freq={freq_fallback}, code={code_fallback}",
            )

        # If everything fails, raise informative error
        raise ValueError(
            f"Failed to decode jammed OKO radar payload: {sanitized_text[:250]}"
        )

    async def disarm_if_locked(self, api_key: str) -> tuple[bool, str | None]:
        """Checks radar lock and neutralizes if active. Returns (was_locked, disarm_hash)."""
        telemetry = await self.check_airspace(api_key)
        if telemetry.is_clear:
            return False, None

        if not telemetry.detection_code or telemetry.frequency is None:
            raise ValueError(
                f"Incomplete telemetry for disarming: freq={telemetry.frequency}, code={telemetry.detection_code}"
            )

        disarm_hash = compute_disarm_hash(telemetry.detection_code)
        logger.info(
            f"Neutralizing OKO radar: freq={telemetry.frequency}, code={telemetry.detection_code} -> SHA-1 disarmHash={disarm_hash}"
        )

        resp = await self.gateway.post_disarm(
            api_key=api_key,
            frequency=telemetry.frequency,
            disarm_hash=disarm_hash,
        )
        logger.info(f"OKO radar disarm response: {resp}")
        return True, disarm_hash
