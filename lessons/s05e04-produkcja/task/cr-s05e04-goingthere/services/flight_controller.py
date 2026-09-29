"""Flight Controller orchestrating the deterministic FSM rocket navigation loop."""

import logging
import re
import time
from typing import Any, Literal
from zoneinfo import ZoneInfo

from langchain_google_genai import ChatGoogleGenerativeAI

from config import config
from schemas import (
    FlightState,
    GameColumn,
    RunTaskRequest,
    RunTaskResponse,
    StartMissionExtraction,
    TrajectoryStep,
)
from services.audit_service import AuditService, generate_session_id
from services.gateway_service import GatewayService
from services.mcp_service import mcp_service
from services.model_armor_service import ModelArmorService
from services.navigator_service import NavigatorService
from services.scanner_service import ScannerService

logger = logging.getLogger("services.flight_controller")
FLAG_REGEX = re.compile(r"\{FLG:[^}]+\}")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


def parse_target_row_from_start_payload(start_resp: dict[str, Any]) -> int:
    """Fallback extraction of target destination row from Centrala start payload."""
    resp_text = str(start_resp)

    # 1. Search for "Grudziadz" or "kolumna 12" followed by row/wiersz
    match_grudziadz = re.search(
        r"""(?:Grudzi[aą]dz|kolumn[a-z]* 12|baza|cel).*?(?:wiersz[a-z]*|row)\s*[:= ]*([1-3])""",
        resp_text,
        re.IGNORECASE,
    )
    if match_grudziadz:
        return int(match_grudziadz.group(1))

    # 2. Search for explicit target / target_row / cel
    match_target = re.search(
        r"""(?:target(?:_row)?|cel)\s*[:= ]*\s*([1-3])""",
        resp_text,
        re.IGNORECASE,
    )
    if match_target:
        return int(match_target.group(1))

    # 3. Check for target_row key in dict
    if isinstance(start_resp, dict) and "target_row" in start_resp:
        try:
            return int(start_resp["target_row"])
        except (ValueError, TypeError):
            pass

    logger.warning(
        f"Could not parse explicit target row from start response ({resp_text[:200]}). Defaulting to Row 2."
    )
    return 2


def select_best_thrust(
    current_row: int,
    target_row: int,
    remaining_columns: int,
    safe_commands: list[Literal["go", "left", "right"]],
    current_col_rock_row: int | None = None,
) -> Literal["go", "left", "right"]:
    """Heuristic path planner selecting optimal vector thrust towards destination."""
    if not safe_commands:
        logger.error(
            "Critical flight emergency: No safe commands available! Forcing 'go' to maintain momentum."
        )
        return "go"

    # HARD SAFETY FILTER (Double defense against corner-cutting collision):
    # A diagonal move into the current column's rock row is a lethal collision.
    if current_col_rock_row is not None:
        strictly_safe = [
            cmd
            for cmd in safe_commands
            if not (cmd == "left" and (current_row - 1) == current_col_rock_row)
            and not (cmd == "right" and (current_row + 1) == current_col_rock_row)
        ]
        if strictly_safe:
            safe_commands = strictly_safe

    if len(safe_commands) == 1:
        return safe_commands[0]

    def command_to_target_row(cmd: Literal["go", "left", "right"]) -> int:
        if cmd == "go":
            return current_row
        if cmd == "left":
            return current_row - 1
        return current_row + 1

    # Score each candidate: (dist_to_target, dist_to_center)
    scored: list[tuple[int, int, Literal["go", "left", "right"]]] = []
    for cmd in safe_commands:
        new_row = command_to_target_row(cmd)
        dist_to_target = abs(target_row - new_row)
        dist_to_center = abs(2 - new_row)
        scored.append((dist_to_target, dist_to_center, cmd))

    scored.sort(key=lambda x: (x[0], x[1]))
    best_cmd = scored[0][2]
    logger.debug(
        f"Candidate thrusts from row {current_row} (target {target_row}, current rock {current_col_rock_row}): {scored} -> selected '{best_cmd}'"
    )
    return best_cmd


def select_suicide_thrust(
    current_row: int, rock_row: int
) -> Literal["go", "left", "right"]:
    """Selects a command guaranteed to intentionally crash into an obstacle or boundary."""
    if rock_row == current_row:
        return "go"
    if rock_row == current_row - 1:
        return "left"
    if rock_row == current_row + 1:
        return "right"
    # If rock is 2 lanes away, steer out of bounds
    if current_row == 1:
        return "left"
    if current_row == 3:
        return "right"
    return "go"


class FlightController:
    """Deterministic Finite State Machine guiding rocket from (1, 2) to (12, target)."""

    def __init__(
        self,
        request: RunTaskRequest | None = None,
        api_key: str | None = None,
        direct_egress: bool = False,
        interactive: bool = False,
        verbose: bool = False,
    ) -> None:
        self.request = request or RunTaskRequest()
        self.api_key = api_key or config.AIDEVS_API_KEY
        self.session_id = self.request.session_id or generate_session_id("fsm")
        self.direct_egress = direct_egress or self.request.direct_egress
        self.interactive = interactive
        self.verbose = verbose
        self.crash_at_column = self.request.crash_at_column

        self.model_name = self.request.model or config.GEMINI_MODEL
        self.thinking_level = self.request.thinking_level or config.THINKING_LEVEL

        self.gateway = GatewayService(direct_egress=self.direct_egress)
        self.model_armor = ModelArmorService()
        self.audit = AuditService()
        self.scanner = ScannerService(
            gateway=self.gateway,
            model_armor=self.model_armor,
            model_name=self.model_name,
            thinking_level=self.thinking_level,
        )
        self.navigator = NavigatorService(
            gateway=self.gateway,
            model_armor=self.model_armor,
            model_name=self.model_name,
            thinking_level=self.thinking_level,
        )

    async def resolve_mission_parameters(
        self, start_resp: dict[str, Any]
    ) -> tuple[int, int | None]:
        """Uses native parsing and LLM structured output to extract target row and initial rock row from start response."""
        resp_text = str(start_resp)
        logger.info(f"Analyzing mission start response: {resp_text}")
        target_row = 2
        start_rock_row = None

        # 1. Direct native extraction from Centrala structured response if present
        if isinstance(start_resp, dict):
            base_dict = start_resp.get("base")
            if isinstance(base_dict, dict) and "row" in base_dict:
                try:
                    b_val = int(base_dict["row"])
                    if b_val in (1, 2, 3):
                        target_row = b_val
                except (ValueError, TypeError):
                    pass
            cur_col_dict = start_resp.get("currentColumn")
            if isinstance(cur_col_dict, dict) and "stoneRow" in cur_col_dict:
                try:
                    s_val = int(cur_col_dict["stoneRow"])
                    if s_val in (1, 2, 3):
                        start_rock_row = s_val
                except (ValueError, TypeError):
                    pass
            if target_row in (1, 2, 3) and start_rock_row in (1, 2, 3):
                logger.info(
                    f"Direct extraction from start response: target_row={target_row}, start_rock_row={start_rock_row}"
                )
                return target_row, start_rock_row

        try:
            llm = ChatGoogleGenerativeAI(
                model=self.model_name,
                temperature=0.1,
                project=config.GOOGLE_CLOUD_PROJECT,
                location=config.GOOGLE_CLOUD_LOCATION,
                vertexai=True,
                thinking_level=self.thinking_level,
            )
            structured_llm = llm.with_structured_output(StartMissionExtraction)
            prompt = (
                "You are an autonomous flight navigation system for an automated rocket.\n"
                "Analyze the mission start payload received from Centrala headquarters.\n"
                "Identify where the rocket starts (start_row), any rock in column 1 (start_rock_row),\n"
                "and WHERE THE TARGET BASE IN GRUDZIADZ (column 12) IS LOCATED (target_row).\n"
                "The target row must be strictly 1 (top), 2 (middle), or 3 (bottom).\n"
                f"Start transmission payload:\n{resp_text}"
            )
            extraction: StartMissionExtraction = await structured_llm.ainvoke(prompt)
            logger.info(
                f"LLM extracted mission parameters: start_row={extraction.start_row}, "
                f"target_row={extraction.target_row}, start_rock_row={extraction.start_rock_row}. "
                f"Reasoning: {extraction.reasoning}"
            )
            if extraction.target_row in (1, 2, 3):
                target_row = extraction.target_row
            if extraction.start_rock_row in (1, 2, 3):
                start_rock_row = extraction.start_rock_row
            return target_row, start_rock_row
        except Exception as exc:
            logger.warning(
                f"LLM mission parameters extraction failed ({exc}). Invoking regex fallback."
            )

        target_row = parse_target_row_from_start_payload(start_resp)
        return target_row, None

    async def resolve_target_row(self, start_resp: dict[str, Any]) -> int:
        """Alias returning target row from start response."""
        target_row, _ = await self.resolve_mission_parameters(start_resp)
        return target_row

    async def probe(self) -> dict[str, Any]:
        """Pre-flight check: sends 'start', verifies connectivity, and prints destination parameters."""
        logger.info("Executing 1-second pre-flight probe...")
        start_resp = await self.gateway.post_verify(
            command="start", api_key=self.api_key
        )
        target_row, _ = await self.resolve_mission_parameters(start_resp)
        print("\n" + "=" * 55)
        print(" [PRE-FLIGHT PROBE SUCCESSFUL]")
        print(f" Status:        Connected to {config.AIDEVS_API_VERIFY}")
        print(" Start Pos:     Column 1, Row 2 (Middle)")
        print(f" Target Base:   Column 12, Row {target_row}")
        print(f" Raw Response:  {start_resp}")
        print("=" * 55 + "\n")
        return {"status": "ok", "target_row": target_row, "raw_response": start_resp}

    async def run_flight(self) -> RunTaskResponse:
        """Executes full autonomous flight across the 3x12 corridor."""
        start_time = time.perf_counter()
        logger.info(
            f"Initiating autonomous flight session {self.session_id} using model {self.model_name} "
            f"(direct_egress={self.direct_egress})"
        )

        self.audit.ensure_table()
        await self.audit.alog_event(
            session_id=self.session_id,
            actor="flight_controller",
            content="Flight mission initialized",
            metadata={"model": self.model_name, "direct_egress": self.direct_egress},
        )

        # 1. Dispatch mission start
        start_resp = await self.gateway.post_verify(
            command="start", api_key=self.api_key
        )
        target_row, start_rock_row = await self.resolve_mission_parameters(start_resp)

        col1_free = (
            [r for r in [1, 2, 3] if r != start_rock_row] if start_rock_row else [1, 2]
        )
        columns_history = {
            1: GameColumn(
                column=1,
                your_row=2,
                stone_row=start_rock_row or 3,
                free_rows=col1_free,
            )
        }

        state = FlightState(
            session_id=self.session_id,
            current_column=1,
            current_row=2,
            target_row=target_row,
            columns_history=columns_history,
            history=[
                TrajectoryStep(
                    column=1,
                    row=2,
                    command="start",
                    rock_row=start_rock_row,
                    radar_locked=False,
                    disarm_hash=None,
                )
            ],
        )

        logger.info(
            f"Mission started: Rocket at (Col 1, Row 2). Destination Grudziadz at (Col 12, Row {target_row}). "
            f"Initial column 1 rock row: {start_rock_row}"
        )

        error_msg: str | None = None

        # 2. Main Traversal Loop (Column 1 to 11 transitions)
        while state.current_column < 12:
            col = state.current_column
            row = state.current_row
            next_col = col + 1

            logger.info(
                f"--- [TRANSITION {col} -> {next_col}] Rocket Altitude: Row {row} | Target: Row {target_row} ---"
            )

            # Phase 1: Radar Interrogation & Disarm
            was_locked, disarm_hash = await self.scanner.disarm_if_locked(self.api_key)
            if was_locked:
                state.radar_disarms_count += 1
                logger.info(
                    f"[Col {col}] Active OKO radar successfully neutralized with hash {disarm_hash}"
                )

            # Phase 2: Radio Telemetry & Obstacle Localization
            raw_hint, nav_telemetry = await self.navigator.get_rock_telemetry(
                api_key=self.api_key,
                current_column=col,
                current_row=row,
                target_row=target_row,
                columns_history=state.columns_history,
            )
            rock_row = nav_telemetry.rock_absolute_row

            # Phase 3: Trajectory Planning (Lookahead Heuristic with Corner-Cutting Guard)
            remaining_cols = 12 - next_col
            if self.crash_at_column is not None and next_col == self.crash_at_column:
                best_cmd = select_suicide_thrust(current_row=row, rock_row=rock_row)
                logger.warning(
                    f"Easter Egg Suicide Trigger: Intentionally crashing at Col {col} -> Col {next_col} via '{best_cmd}' (rock at Row {rock_row})"
                )
            else:
                best_cmd = select_best_thrust(
                    current_row=row,
                    target_row=target_row,
                    remaining_columns=remaining_cols,
                    safe_commands=nav_telemetry.safe_commands,
                    current_col_rock_row=state.current_rock_row,
                )

            # Interactive Step-by-Step Dashboard
            if self.interactive:
                print("\n" + "-" * 55)
                print(
                    f" [COLUMN {col} -> {next_col}] ALTITUDE: Row {row} (Target: Row {target_row})"
                )
                radar_str = (
                    f"LOCKED -> DISARMED ({disarm_hash})" if was_locked else "CLEAR"
                )
                print(f" Radar OKO:    {radar_str}")
                print(f" Radio Hint:   '{raw_hint}'")
                print(
                    f" Rock Ahead:   Row {rock_row} ({nav_telemetry.rock_relative_direction})"
                )
                print(f" Safe Moves:   {nav_telemetry.safe_commands}")
                print(f" Thrust Vector: >>> {best_cmd.upper()} <<<")
                print("-" * 55)
                input("Press [Enter] to dispatch thrust command...")

            # Phase 4: Vector Thrust Dispatch & State Transition
            thrust_resp = await self.gateway.post_verify(
                command=best_cmd, api_key=self.api_key
            )
            resp_msg = str(thrust_resp.get("message") or thrust_resp)

            # Check for flag at any transition (including crash or secret response)
            flag_match = FLAG_REGEX.search(resp_msg)
            if flag_match:
                state.flag = flag_match.group(0)
                state.is_completed = True
                logger.info("Successfully acquired mission flag: [REDACTED_FLAG]")
                break

            # Check for crash or failure
            if (
                "rozbi" in resp_msg.lower()
                or "zestrzel" in resp_msg.lower()
                or "crash" in resp_msg.lower()
            ):
                error_msg = f"Rocket destroyed during thrust '{best_cmd}' to column {next_col}: {resp_msg}"
                logger.error(error_msg)
                break

            # Compute new row
            new_row = (
                row
                if best_cmd == "go"
                else (row - 1 if best_cmd == "left" else row + 1)
            )
            state.current_column = next_col
            state.current_row = new_row

            # Record sector history for subsequent relative/temporal hints
            next_col_free = [r for r in [1, 2, 3] if r != rock_row] if rock_row else []
            state.columns_history[next_col] = GameColumn(
                column=next_col,
                your_row=new_row,
                stone_row=rock_row,
                free_rows=next_col_free,
            )

            state.history.append(
                TrajectoryStep(
                    column=next_col,
                    row=new_row,
                    command=best_cmd,
                    rock_row=rock_row,
                    radar_locked=was_locked,
                    disarm_hash=disarm_hash,
                )
            )

            logger.info(
                f"FlightState [Col {next_col}, Row {new_row}]:\n{state.model_dump_json(indent=2)}"
            )

            await self.audit.alog_event(
                session_id=self.session_id,
                actor="flight_controller",
                content=f"Advanced to Col {next_col}, Row {new_row} via '{best_cmd}'",
                metadata={
                    "column": next_col,
                    "row": new_row,
                    "command": best_cmd,
                    "rock_row": rock_row,
                    "was_radar_locked": was_locked,
                    "flight_state": state.model_dump(),
                },
            )

            # Check for flag at destination
            flag_match = FLAG_REGEX.search(resp_msg)
            if flag_match:
                state.flag = flag_match.group(0)
                state.is_completed = True
                logger.info("Successfully acquired mission flag: [REDACTED_FLAG]")
                break

        exec_time = round(time.perf_counter() - start_time, 2)
        status: Literal["completed", "failed"] = (
            "completed" if state.is_completed or state.flag else "failed"
        )

        # Construct run notes
        run_notes_content = f"""# Flight Log: {config.TASK_NAME} (S05E04)
Timestamp: {time.strftime("%Y-%m-%d %H:%M:%S")}
Session ID: {self.session_id}
Status: {status.upper()}
Target Base: Column 12, Row {state.target_row}
Total Steps: {len(state.history) - 1}
Radar Disarms: {state.radar_disarms_count}
Execution Time: {exec_time}s
Flag: {state.flag or "[NONE]"}
Error: {error_msg or "None"}

## Trajectory History
| Column | Row | Action | Rock Row | Radar Locked | Disarm Hash |
| :---: | :---: | :---: | :---: | :---: | :---: |
"""
        for step in state.history:
            run_notes_content += (
                f"| {step.column} | {step.row} | `{step.command}` | {step.rock_row or '-'} | "
                f"{'YES' if step.radar_locked else 'NO'} | `{step.disarm_hash or '-'}` |\n"
            )

        # Mandatory persistence to cr-mcp-workspace (GCS)
        try:
            await mcp_service.write_file(
                session_id=self.session_id,
                file_path="run_notes.txt",
                content=run_notes_content,
                reasoning=f"Persisting flight run notes for session {self.session_id}",
            )
        except Exception as exc:
            logger.warning(
                f"Could not persist run_notes.txt to cr-mcp-workspace ({exc}). "
                "Local disk write is skipped per Zero Disk Poisoning rule."
            )

        await self.audit.alog_event(
            session_id=self.session_id,
            actor="flight_controller",
            content=f"Mission finished with status={status}",
            metadata={
                "status": status,
                "total_steps": len(state.history) - 1,
                "flag_acquired": bool(state.flag),
            },
        )

        return RunTaskResponse(
            session_id=self.session_id,
            status=status,
            flag=state.flag,
            target_row=state.target_row,
            total_steps=len(state.history) - 1,
            radar_disarms=state.radar_disarms_count,
            trajectory=state.history,
            execution_time_seconds=exec_time,
            error=error_msg,
        )
