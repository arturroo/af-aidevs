from typing import List, Tuple
from af_aidevs.schemas.vision import TilePinout, GridCircuitSolverData
from schemas import RotateCommand


def rotate_pinout_cw(pins: TilePinout, steps: int = 1) -> TilePinout:
    """Rotates a tile's 4-way pinout clockwise by 90 degrees * (steps % 4)."""
    k = steps % 4
    t, r, b, l = pins.top, pins.right, pins.bottom, pins.left
    for _ in range(k):
        t, r, b, l = l, t, r, b
    return TilePinout(top=t, right=r, bottom=b, left=l)


def calculate_tile_rotation_delta(current_pins: TilePinout, target_pins: TilePinout) -> Tuple[int, float]:
    """
    Computes minimal 90-degree CW rotations (0-3) to match target_pins.
    Returns (steps_cw, match_confidence).
    """
    for steps in range(4):
        rotated = rotate_pinout_cw(current_pins, steps)
        if (
            rotated.top == target_pins.top
            and rotated.right == target_pins.right
            and rotated.bottom == target_pins.bottom
            and rotated.left == target_pins.left
        ):
            return steps, 1.0

    # No exact match found
    return 0, 0.0


def compute_board_rotations(
    current_board: List[List[TilePinout]],
    target_board: List[List[TilePinout]],
    raw_confidence: List[List[float]],
) -> GridCircuitSolverData:
    """Calculates the full 3x3 rotation matrix and confidence scores."""
    rotations_matrix: List[List[int]] = []
    tile_conf_matrix: List[List[float]] = []

    for r in range(3):
        row_rots: List[int] = []
        row_confs: List[float] = []
        for c in range(3):
            curr_p = current_board[r][c]
            targ_p = target_board[r][c]
            steps, match_conf = calculate_tile_rotation_delta(curr_p, targ_p)
            combined_conf = float(raw_confidence[r][c] * match_conf)
            row_rots.append(steps)
            row_confs.append(combined_conf)
        rotations_matrix.append(row_rots)
        tile_conf_matrix.append(row_confs)

    all_confs = [c for row in tile_conf_matrix for c in row]
    overall_conf = float(sum(all_confs) / len(all_confs)) if all_confs else 0.0

    return GridCircuitSolverData(
        rotations=rotations_matrix,
        confidence=overall_conf,
        tile_confidence=tile_conf_matrix,
    )


def generate_rotation_commands(rotations: List[List[int]]) -> List[RotateCommand]:
    """Extracts non-zero rotation commands formatted as AxB coordinates."""
    commands: List[RotateCommand] = []
    for r_idx, row in enumerate(rotations, start=1):
        for c_idx, steps in enumerate(row, start=1):
            if steps > 0:
                commands.append(RotateCommand(tile_id=f"{r_idx}x{c_idx}", steps_cw=steps))
    return commands
