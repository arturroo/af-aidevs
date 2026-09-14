import logging
from typing import Dict, Tuple
from schemas import BlockState, CommandType
from services.pathfinding_service import (
    GRID_COLS,
    PathfindingService,
    predict_block_positions,
)

logger = logging.getLogger("services.guardrail")


class SafetyGuardrailService:
    """Pre-flight safety guardrail evaluating commands against discrete block kinematics at t+1."""

    @classmethod
    def validate_command(
        cls,
        current_col: int,
        command: CommandType,
        current_blocks: Dict[int, BlockState],
    ) -> Tuple[bool, str, int]:
        """Validates if `command` is safe to execute from `current_col`.

        Returns: (is_safe, explanation, target_column)
        """
        # Determine target column
        if command == "right":
            target_col = current_col + 1
        elif command == "left":
            target_col = current_col - 1
        elif command == "wait":
            target_col = current_col
        elif command in ("start", "reset"):
            # Administrative simulation commands are inherently safe from spatial collisions
            return True, f"Command '{command}' is administrative and spatially safe.", current_col
        else:
            return False, f"Unknown command '{command}'.", current_col

        # Check chamber boundaries
        if target_col < 1 or target_col > GRID_COLS:
            return (
                False,
                f"Boundary Violation: Command '{command}' attempts to move out of grid bounds (target column {target_col}).",
                current_col,
            )

        # Simulate obstacle positions at t+1
        predicted_blocks = predict_block_positions(current_blocks, steps_ahead=1)

        # Check if target column floor (Row 5) is occupied by a block
        if PathfindingService.is_floor_blocked(predicted_blocks, target_col):
            block = predicted_blocks[target_col]
            return (
                False,
                f"Collision Hazard: Command '{command}' to Column {target_col} will collide with reactor block {block} reaching Row 5 at step t+1. Move rejected.",
                target_col,
            )

        return (
            True,
            f"Move verified: Column {target_col} will be clear of reactor blocks at step t+1.",
            target_col,
        )
