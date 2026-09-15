from collections import deque
import logging
from typing import Dict, List, Optional, Tuple
from schemas import BlockState, BoardState, CommandType

logger = logging.getLogger("services.pathfinding")

GRID_COLS = 7
GRID_ROWS = 5
CYCLE_PERIOD = 6  # For 2-cell block oscillating between rows 1 and 5 (top_row in 1..4)


def step_single_block(top_row: int, direction: str) -> Tuple[int, str]:
    """Computes the next vertical top_row (1..4) and direction ('up'/'down') for a 2-cell block."""
    if top_row == 4:
        # Reached lowest position (occupying rows 4 & 5), must bounce up
        return 3, "up"
    elif top_row == 1:
        # Reached highest position (occupying rows 1 & 2), must bounce down
        return 2, "down"
    elif direction == "down":
        next_row = top_row + 1
        return (next_row, "up" if next_row == 4 else "down")
    else:  # direction == "up"
        next_row = top_row - 1
        return (next_row, "down" if next_row == 1 else "up")


def predict_block_positions(
    initial_blocks: Dict[int, BlockState], steps_ahead: int
) -> Dict[int, BlockState]:
    """Simulates block kinematics forward by `steps_ahead` command turns."""
    current = {
        col: BlockState(
            column=b.column, top_row=b.top_row, direction=b.direction
        )
        for col, b in initial_blocks.items()
    }

    for _ in range(steps_ahead):
        next_blocks = {}
        for col, b in current.items():
            next_row, next_dir = step_single_block(b.top_row, b.direction)
            next_blocks[col] = BlockState(
                column=col, top_row=next_row, direction=next_dir
            )
        current = next_blocks

    return current


class PathfindingService:
    """State-Space BFS solver providing deterministic, collision-free trajectory planning."""

    @staticmethod
    def is_floor_blocked(blocks: Dict[int, BlockState], col: int) -> bool:
        """Returns True if a block in `col` currently occupies floor row 5 (top_row == 4)."""
        block = blocks.get(col)
        if not block:
            return False
        return block.top_row == 4

    @classmethod
    def find_shortest_safe_path(
        cls,
        start_col: int,
        target_col: int,
        current_blocks: Dict[int, BlockState],
        max_horizon: int = 50,
    ) -> Optional[List[CommandType]]:
        """Finds the optimal collision-free sequence of commands [right, wait, left] to reach target_col.

        Uses State-Space Breadth-First Search over (col, time_step % 6).
        """
        if start_col == target_col:
            return []

        # Pre-compute block states for each time step modulo 6
        cycle_block_states: List[Dict[int, BlockState]] = []
        for t in range(CYCLE_PERIOD):
            cycle_block_states.append(predict_block_positions(current_blocks, t))

        # BFS queue: (col, t, path)
        queue: deque[Tuple[int, int, List[CommandType]]] = deque()
        queue.append((start_col, 0, []))

        # Visited states: (col, t % CYCLE_PERIOD)
        visited = set()
        visited.add((start_col, 0))

        while queue:
            col, t, path = queue.popleft()

            if t >= max_horizon:
                continue

            next_t = t + 1
            next_phase = next_t % CYCLE_PERIOD
            blocks_at_next = cycle_block_states[next_phase]

            # Allowed transitions: right, wait, left (prefer right to reach goal faster)
            candidates: List[Tuple[CommandType, int]] = []
            if col < GRID_COLS:
                candidates.append(("right", col + 1))
            candidates.append(("wait", col))
            if col > 1:
                candidates.append(("left", col - 1))

            for cmd, next_col in candidates:
                # Check collision at step t+1: block in next_col must NOT occupy row 5
                if cls.is_floor_blocked(blocks_at_next, next_col):
                    continue

                if next_col == target_col:
                    return path + [cmd]

                state_key = (next_col, next_phase)
                if state_key not in visited:
                    visited.add(state_key)
                    queue.append((next_col, next_t, path + [cmd]))

        logger.warning(
            f"No safe path found from col={start_col} to col={target_col} within horizon={max_horizon}"
        )
        return None

    @classmethod
    def parse_blocks_from_map(
        cls,
        raw_map: List[str],
        known_directions: Optional[Dict[int, str]] = None,
    ) -> Dict[int, BlockState]:
        """Parses ASCII chamber map (5 rows of 7 chars) into typed BlockState dictionary.

        Rows 1 to 5, Columns 1 to 7.
        """
        blocks: Dict[int, BlockState] = {}
        directions = known_directions or {}

        # Search each column 0..6
        for col_idx in range(min(GRID_COLS, len(raw_map[0]) if raw_map else 0)):
            col_num = col_idx + 1
            b_rows = []
            for row_idx, line in enumerate(raw_map):
                if col_idx < len(line) and line[col_idx] == "B":
                    b_rows.append(row_idx + 1)  # 1-indexed row

            if b_rows:
                top_row = min(b_rows)
                direction = directions.get(col_num, "down")
                if top_row == 4:
                    direction = "up"
                elif top_row == 1:
                    direction = "down"

                blocks[col_num] = BlockState(
                    column=col_num,
                    top_row=top_row,
                    direction=direction,
                )

        return blocks
