"""Service for fetching radio hints and translating maritime terminology into rock coordinates."""

import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from config import config
from schemas import GameColumn, RadioNavigationExtraction
from services.gateway_service import GatewayService
from services.model_armor_service import ModelArmorService

logger = logging.getLogger("services.navigator")

NAVIGATOR_SYSTEM_PROMPT = """You are an expert naval tactical flight navigator piloting a ground-skimming rocket through a 3-row flight corridor:
- Row 1: Top / High channel (Portmost outer lane)
- Row 2: Middle / Center channel (Centerline / Central fairway)
- Row 3: Bottom / Low channel (Starboardmost outer lane)

Every movement advances forward by 1 column. In each upcoming column, there is exactly ONE lethal rock formation. Exactly two rows are clear and safe.

The tactical radio broadcast describes where the rock obstacle is in the upcoming column:
1. MARITIME & SPATIAL TERMS (Relative to current rocket position):
   - If rocket is at Row 2 (Center):
     * "Ahead / bow / straight / nose / dead ahead / center / front / direct": Rock is in Row 2. Safe moves: 'left' (Row 1), 'right' (Row 3).
     * "Port / left / high / top / above": Rock is in Row 1. Safe moves: 'go' (Row 2), 'right' (Row 3).
     * "Starboard / right / low / bottom / below": Rock is in Row 3. Safe moves: 'go' (Row 2), 'left' (Row 1).
     * "Both side lanes free / problem in the center": Rock is in Row 2. Safe moves: 'left' (Row 1), 'right' (Row 3).
   - If rocket is at Row 1 (Top / High):
     * "Ahead / straight / nose / route in front blocked": Rock is in Row 1. Safe move: strictly 'right' (Row 2). ('left' is out of bounds).
     * "Starboard / right / below / low / side hazard": Rock is in Row 2 or Row 3 (the route directly ahead in Row 1 is clear!). Safe move: 'go' (Row 1).
     * "Route in front clear / area to port clear": Row 1 is safe! Safe move: 'go' (Row 1).
   - If rocket is at Row 3 (Bottom / Low):
     * "Ahead / straight / nose / route in front blocked": Rock is in Row 3. Safe move: strictly 'left' (Row 2). ('right' is out of bounds).
     * "Port / left / above / high / side hazard": Rock is in Row 1 or Row 2 (the route directly ahead in Row 3 is clear!). Safe move: 'go' (Row 3).
     * "Route in front clear / area to starboard clear": Row 3 is safe! Safe move: 'go' (Row 3).

2. TEMPORAL & RELATIVE HISTORICAL REFERENCES:
   - If the radio hint references a previous column (e.g. "same as start / launch", "same row as column 1", "mirrors two columns back", "returned to the channel from step X"):
     * Cross-reference the KNOWN FLIGHT SECTOR MAP provided in the user dispatch to look up that exact column's rock position and set 'rock_absolute_row' accordingly!

Your task:
1. Carefully analyze the radio hint from the perspective of an experienced navigator using both spatial terms and the sector map history.
2. Determine 'rock_relative_direction': 'left', 'ahead', or 'right'.
3. Determine 'rock_absolute_row': strictly 1, 2, or 3.
4. Determine 'safe_commands': subset of ['go', 'left', 'right'] that do NOT hit the rock and do NOT fly outside rows 1-3.
5. Provide your nautical and historical interpretation in 'reasoning'.
"""


def format_columns_history(columns_history: dict[int, GameColumn] | None) -> str:
    """Formats cumulative column history for prompt injection."""
    if not columns_history:
        return "No prior columns traversed yet."
    lines: list[str] = []
    for col_idx in sorted(columns_history.keys()):
        col_data = columns_history[col_idx]
        free_str = (
            ", ".join(map(str, col_data.free_rows)) if col_data.free_rows else "unknown"
        )
        lines.append(
            f"- Column {col_data.column}: Rocket was at Row {col_data.your_row} | Rock at Row {col_data.stone_row} | Free Rows [{free_str}]"
        )
    return "\n".join(lines)


def compute_safe_moves_from_rock_row(
    current_row: int,
    rock_row: int,
    current_col_rock_row: int | None = None,
) -> list[Literal["go", "left", "right"]]:
    """Calculates collision-free moves given current row, next column obstacle row, and current column rock.

    A diagonal move ('left' or 'right') requires:
    1. The target row is within vertical grid boundaries (1 <= row <= 3).
    2. The target row in the NEXT column does not hit a rock (target != rock_row).
    3. The target row in the CURRENT column does not cut the corner of an existing rock (target != current_col_rock_row).
    """
    safe: list[Literal["go", "left", "right"]] = []
    # Candidate 'go' (remains at current_row)
    if current_row != rock_row:
        safe.append("go")
    # Candidate 'left' (climbs to row - 1)
    if (
        current_row > 1
        and (current_row - 1) != rock_row
        and (current_col_rock_row is None or (current_row - 1) != current_col_rock_row)
    ):
        safe.append("left")
    # Candidate 'right' (descends to row + 1)
    if (
        current_row < 3
        and (current_row + 1) != rock_row
        and (current_col_rock_row is None or (current_row + 1) != current_col_rock_row)
    ):
        safe.append("right")

    if not safe:
        # Emergency fallback to single-step lookahead if dual constraints yield no safe paths
        fallback: list[Literal["go", "left", "right"]] = []
        if current_row != rock_row:
            fallback.append("go")
        if current_row > 1 and (current_row - 1) != rock_row:
            fallback.append("left")
        if current_row < 3 and (current_row + 1) != rock_row:
            fallback.append("right")
        return fallback

    return safe


def heuristic_nautical_fallback(
    hint_text: str,
    current_row: int,
    current_col_rock_row: int | None = None,
) -> RadioNavigationExtraction:
    """Heuristic rule-based fallback mapping nautical keywords to rock row."""
    text = hint_text.lower()

    if any(k in text for k in ["port", "left", "high", "above", "top"]):
        rel_dir: Literal["left", "ahead", "right", "unknown"] = "left"
        rock_row = max(1, current_row - 1)
    elif any(k in text for k in ["starboard", "right", "low", "below", "bottom"]):
        rel_dir = "right"
        rock_row = min(3, current_row + 1)
    elif any(
        k in text
        for k in ["ahead", "bow", "straight", "center", "middle", "front", "stern"]
    ):
        rel_dir = "ahead"
        rock_row = current_row
    else:
        rel_dir = "ahead"
        rock_row = current_row

    safe_moves = compute_safe_moves_from_rock_row(
        current_row, rock_row, current_col_rock_row=current_col_rock_row
    )
    return RadioNavigationExtraction(
        rock_relative_direction=rel_dir,
        rock_absolute_row=rock_row,
        safe_commands=safe_moves,
        reasoning=f"Heuristic keyword fallback for: '{hint_text}'",
    )


class NavigatorService:
    """Interprets tactical radio broadcasts and determines rock positions and safe thrust vectors."""

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

    async def get_rock_telemetry(
        self,
        api_key: str,
        current_column: int,
        current_row: int,
        target_row: int = 2,
        columns_history: dict[int, GameColumn] | None = None,
    ) -> tuple[str, RadioNavigationExtraction]:
        """Queries radio message and resolves rock position in current_column + 1."""
        resp = await self.gateway.post_getmessage(api_key)
        raw_hint = str(resp.get("hint") or resp.get("message") or "").strip()
        logger.info(
            f"[Col {current_column} -> {current_column + 1}] Radio broadcast received: '{raw_hint}'"
        )

        if not raw_hint:
            raise ValueError(f"Empty radio hint received from Centrala: {resp}")

        # Sanitize hint against prompt injection
        sanitized_hint = await self.model_armor.sanitize_payload(
            raw_hint, context="radio_broadcast"
        )

        next_column = current_column + 1
        human_content = (
            f"MISSION FLIGHT STATUS:\n"
            f"- Current Position: Column {current_column}, Row {current_row}\n"
            f"- Destination Base: Column 12, Row {target_row}\n"
            f"- Approaching Target Column: {next_column}\n\n"
            f"SECTOR MAP (PREVIOUS TRAVERSED COLUMNS HISTORY):\n"
            f"{format_columns_history(columns_history)}\n\n"
            f"TACTICAL RADIO TRANSMISSION FOR UPCOMING COLUMN {next_column}:\n"
            f"'{sanitized_hint}'"
        )

        try:
            llm = self._get_llm()
            structured_llm = llm.with_structured_output(RadioNavigationExtraction)
            messages = [
                SystemMessage(content=NAVIGATOR_SYSTEM_PROMPT),
                HumanMessage(content=human_content),
            ]
            extraction: RadioNavigationExtraction = await structured_llm.ainvoke(
                messages
            )
            current_col_rock = (
                columns_history[current_column].stone_row
                if columns_history and current_column in columns_history
                else None
            )
            # Ensure safe commands are strictly validated against both bounds and obstacle geometry
            calculated_safe = compute_safe_moves_from_rock_row(
                current_row=current_row,
                rock_row=extraction.rock_absolute_row,
                current_col_rock_row=current_col_rock,
            )
            extraction.safe_commands = calculated_safe
            logger.info(
                f"Nautical resolution: rock is at Row {extraction.rock_absolute_row} ({extraction.rock_relative_direction}). "
                f"Safe moves (current rock {current_col_rock}): {extraction.safe_commands}. Reasoning: {extraction.reasoning[:120]}"
            )
            return raw_hint, extraction
        except Exception as exc:
            logger.warning(
                f"LLM nautical resolution failed ({exc}). Using heuristic fallback for hint: '{sanitized_hint}'"
            )
            current_col_rock = (
                columns_history[current_column].stone_row
                if columns_history and current_column in columns_history
                else None
            )
            fallback = heuristic_nautical_fallback(
                sanitized_hint,
                current_row,
                current_col_rock_row=current_col_rock,
            )
            return raw_hint, fallback
