"""Response Guardrail enforcing Centrala's strict byte envelope constraints.

Every tool response returned to Centrala's agent must satisfy:
    4 <= len(response.encode('utf-8')) <= 500
"""

import logging

logger = logging.getLogger(__name__)

MIN_BYTE_LEN = 4
MAX_BYTE_LEN = 500
TRUNCATION_SAFE_THRESHOLD = 480


def get_byte_length(text: str) -> int:
    """Return UTF-8 encoded byte length of string."""
    return len(text.encode("utf-8"))


def validate_byte_bounds(text: str) -> bool:
    """Check if string satisfies 4 <= len(utf-8 bytes) <= 500."""
    byte_len = get_byte_length(text)
    return MIN_BYTE_LEN <= byte_len <= MAX_BYTE_LEN


def enforce_byte_envelope(text: str, fallback_if_empty: str = "Brak danych.") -> str:
    """Enforce strict [4, 500] UTF-8 byte boundary on response strings.

    - If text is under 4 bytes, replaces with safe fallback.
    - If text exceeds 500 bytes, slices safely under 480 bytes at word boundary and appends '...'.
    """
    if not text:
        text = fallback_if_empty

    raw_bytes = text.encode("utf-8")
    if len(raw_bytes) < MIN_BYTE_LEN:
        logger.warning(
            "Response too short (%d bytes), applying fallback padding.", len(raw_bytes)
        )
        return fallback_if_empty

    if len(raw_bytes) <= MAX_BYTE_LEN:
        return text

    logger.warning(
        "Response exceeded 500 bytes (%d bytes). Enforcing graceful truncation.",
        len(raw_bytes),
    )

    # Decode safely up to safe threshold
    truncated_bytes = raw_bytes[:TRUNCATION_SAFE_THRESHOLD]
    # Decode ignoring broken trailing multi-byte characters
    truncated_text = truncated_bytes.decode("utf-8", errors="ignore")

    # Cut back to last space to avoid broken words
    last_space = truncated_text.rfind(" ")
    if last_space > 0:
        truncated_text = truncated_text[:last_space]

    final_text = f"{truncated_text.rstrip()}..."
    final_bytes = final_text.encode("utf-8")

    # Safety assertion
    if len(final_bytes) > MAX_BYTE_LEN:
        final_text = final_bytes[:MAX_BYTE_LEN].decode("utf-8", errors="ignore")

    return final_text
