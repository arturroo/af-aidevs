import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import config
from schemas import BlockState, BoardState, CommandType
from services.mcp_service import MCPService
from services.pathfinding_service import GRID_COLS, GRID_ROWS, PathfindingService

logger = logging.getLogger("services.reactor")


class ReactorService:
    """Client managing turn-based reactor navigation via cr-mcp-web-gateway."""

    def __init__(self, mcp_service: MCPService):
        self.mcp = mcp_service
        self.last_board_state: Optional[BoardState] = None
        self.known_directions: Dict[int, str] = {}
        self.step_counter: int = 0
        self.flag: Optional[str] = None

    async def send_command(
        self, session_id: str, command: CommandType
    ) -> Tuple[BoardState, bool, bool, Optional[str]]:
        """Sends a navigation command to $AIDEVS_API_VERIFY via cr-mcp-web-gateway.

        Returns: (board_state, is_goal_reached, is_collision, flag)
        """
        payload = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": {"command": command},
        }

        logger.info(
            f"Dispatching command '{command}' for session={session_id} to {config.AIDEVS_VERIFY_URL} via cr-mcp-web-gateway"
        )
        raw_resp = await self.mcp.post_web_resource(
            session_id=session_id,
            url=config.AIDEVS_VERIFY_URL,
            payload=payload,
        )

        board_state, is_goal_reached, is_collision, flag = self._parse_api_response(
            raw_resp, command
        )
        if flag:
            self.flag = flag

        self.last_board_state = board_state
        return board_state, is_goal_reached, is_collision, flag

    def _parse_api_response(
        self, resp: Dict[str, Any], command: CommandType
    ) -> Tuple[BoardState, bool, bool, Optional[str]]:
        """Parses the API response into a structured BoardState, detecting goal, collision, and flag."""
        message = str(resp.get("message") or resp.get("details") or "")
        resp_str = json.dumps(resp)

        # Detect flag
        flag_match = re.search(r"(\{FLG:[^\}]+\})", resp_str)
        flag = flag_match.group(1) if flag_match else None

        # Check collision
        is_collision = False
        lower_msg = (message + " " + resp_str).lower()
        if any(w in lower_msg for w in ["collision", "crushed", "zgnieciony", "zniszczony", "dead", "game over"]):
            is_collision = True

        # Extract map representation
        raw_map: List[str] = []
        if isinstance(resp.get("map"), list):
            raw_map = [str(line).strip() for line in resp["map"]]
        elif isinstance(resp.get("board"), list):
            raw_map = [str(line).strip() for line in resp["board"]]
        elif isinstance(resp.get("map"), str):
            raw_map = [line.strip() for line in resp["map"].strip().splitlines() if line.strip()]
        else:
            # Look for 5 consecutive lines containing chamber symbols
            lines = [l.strip() for l in message.splitlines() if l.strip()]
            candidate_map = [l for l in lines if len(l) == GRID_COLS and all(c in ".BPG12345" for c in l)]
            if len(candidate_map) == GRID_ROWS:
                raw_map = candidate_map

        # Parse robot column and blocks
        robot_col = 1
        blocks_dict: Dict[int, BlockState] = {}

        # 1. Check if blocks are explicitly provided as structured objects
        if "blocks" in resp and isinstance(resp["blocks"], list):
            for b in resp["blocks"]:
                if isinstance(b, dict) and "column" in b and "top_row" in b:
                    c_num = int(b["column"])
                    direction = str(b.get("direction", "down")).lower()
                    blocks_dict[c_num] = BlockState(
                        column=c_num,
                        top_row=int(b["top_row"]),
                        direction="up" if "up" in direction else "down",
                    )

        # 2. Parse from ASCII map if present
        if raw_map and len(raw_map) >= GRID_ROWS:
            # Identify robot position ('P' or bottom indicator)
            floor_row = raw_map[GRID_ROWS - 1]
            for c_idx, char in enumerate(floor_row[:GRID_COLS]):
                if char == "P":
                    robot_col = c_idx + 1

            # Parse block positions from map
            parsed_blocks = PathfindingService.parse_blocks_from_map(
                raw_map, known_directions=self.known_directions
            )

            # Update directions based on history if available
            if self.last_board_state:
                prev_blocks = {b.column: b for b in self.last_board_state.blocks}
                for c_num, cur_b in parsed_blocks.items():
                    if c_num in prev_blocks:
                        prev_top = prev_blocks[c_num].top_row
                        if cur_b.top_row > prev_top:
                            cur_b.direction = "down"
                        elif cur_b.top_row < prev_top:
                            cur_b.direction = "up"
                        else:
                            # Reached boundary
                            cur_b.direction = "up" if cur_b.top_row == 4 else "down"
                    self.known_directions[c_num] = cur_b.direction

            blocks_dict.update(parsed_blocks)

        # Increment simulation step
        if command != "start" and command != "reset":
            self.step_counter += 1
        else:
            self.step_counter = 0

        # Goal is reached if robot is in column 7 or flag is returned or message indicates success
        is_goal = False
        if robot_col == GRID_COLS or flag is not None or "success" in lower_msg or "gratulacj" in lower_msg:
            is_goal = True

        board_state = BoardState(
            step=self.step_counter,
            robot_column=robot_col,
            robot_row=GRID_ROWS,
            blocks=list(blocks_dict.values()),
            raw_map=raw_map if raw_map else None,
            message=message,
        )

        return board_state, is_goal, is_collision, flag
