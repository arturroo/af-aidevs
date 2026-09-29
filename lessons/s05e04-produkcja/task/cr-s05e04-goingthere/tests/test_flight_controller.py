"""Unit tests for flight controller FSM, target row parsing, and heuristic trajectory selection."""

from services.flight_controller import (
    parse_target_row_from_start_payload,
    select_best_thrust,
    select_suicide_thrust,
)
from services.navigator_service import compute_safe_moves_from_rock_row


def test_parse_target_row_from_polish_start_message() -> None:
    msg1 = {
        "message": "Baza w Grudziądzu znajduje się w kolumnie 12, wiersz 1. Powodzenia!"
    }
    assert parse_target_row_from_start_payload(msg1) == 1

    msg2 = {"message": "Start gry. Cel: Grudziadz, kolumna 12, wierszu 3."}
    assert parse_target_row_from_start_payload(msg2) == 3

    msg3 = {"target_row": 2, "message": "Game started"}
    assert parse_target_row_from_start_payload(msg3) == 2

    msg4 = {
        "message": "Twoja pozycja: kolumna 1, wiersz 2. Baza w Grudziądzu znajduje się w kolumnie 12, wiersz 3."
    }
    assert parse_target_row_from_start_payload(msg4) == 3


def test_select_best_thrust_steers_towards_target() -> None:
    # Current Row 2, Target Row 1, Safe commands: ['go', 'left']
    # 'left' leads to Row 1 (dist 0), 'go' leads to Row 2 (dist 1)
    best = select_best_thrust(
        current_row=2,
        target_row=1,
        remaining_columns=5,
        safe_commands=["go", "left"],
    )
    assert best == "left"


def test_select_best_thrust_maintains_target_row() -> None:
    # Current Row 1, Target Row 1, Safe commands: ['go', 'right']
    # 'go' leads to Row 1 (dist 0), 'right' leads to Row 2 (dist 1)
    best = select_best_thrust(
        current_row=1,
        target_row=1,
        remaining_columns=3,
        safe_commands=["go", "right"],
    )
    assert best == "go"


def test_select_best_thrust_steers_downwards_towards_bottom() -> None:
    # Current Row 2, Target Row 3, Safe commands: ['go', 'right']
    best = select_best_thrust(
        current_row=2,
        target_row=3,
        remaining_columns=4,
        safe_commands=["go", "right"],
    )
    assert best == "right"


def test_select_best_thrust_prefers_closer_target_row() -> None:
    # Current Row 2, Target Row 3, Safe commands: ['left', 'right']
    # 'left' leads to Row 1 (dist 2), 'right' leads to Row 3 (dist 0)
    best = select_best_thrust(
        current_row=2,
        target_row=3,
        remaining_columns=5,
        safe_commands=["left", "right"],
    )
    assert best == "right"


def test_select_best_thrust_avoids_corner_cutting_rock_in_current_column() -> None:
    # Current Row 2, Target Row 2 (equidistant to Row 1 and Row 3)
    # Both 'left' (Row 1) and 'right' (Row 3) are safe in next column.
    # But current column has rock at Row 1 (current_col_rock_row = 1).
    # Turning 'left' would cut the corner of the rock at Row 1.
    # Therefore, 'right' (Row 3) MUST be chosen!
    best = select_best_thrust(
        current_row=2,
        target_row=2,
        remaining_columns=5,
        safe_commands=["left", "right"],
        current_col_rock_row=1,
    )
    assert best == "right"

    # Conversely, if rock was at Row 3 (current_col_rock_row = 3), 'left' MUST be chosen!
    best_left = select_best_thrust(
        current_row=2,
        target_row=2,
        remaining_columns=5,
        safe_commands=["left", "right"],
        current_col_rock_row=3,
    )
    assert best_left == "left"


def test_select_best_thrust_overrides_target_row_when_corner_blocked() -> None:
    # Real crash scenario:
    # Current Row 2, Target Row 1.
    # Safe moves in next column are ['left', 'right'] (rock ahead at Row 2).
    # BUT current column has rock at Row 1 (current_col_rock_row = 1).
    # Even though Row 1 is the destination base (dist 0), turning 'left' cuts the corner
    # of the rock at (col, 1) and causes an immediate fatal crash.
    # The hard safety filter MUST drop 'left' and choose 'right' (Row 3).
    best = select_best_thrust(
        current_row=2,
        target_row=1,
        remaining_columns=7,
        safe_commands=["left", "right"],
        current_col_rock_row=1,
    )
    assert best == "right"


def test_synthetic_grid_simulation_full_12_columns() -> None:
    """Simulates a full 12-column grid to ensure rocket reaches target row without collisions."""
    # Obstacle row per column (columns 2 to 12)
    grid_obstacles = {
        2: 2,  # Col 2 rock is at row 2
        3: 1,  # Col 3 rock is at row 1
        4: 3,  # Col 4 rock is at row 3
        5: 2,  # Col 5 rock is at row 2
        6: 1,  # Col 6 rock is at row 1
        7: 3,  # Col 7 rock is at row 3
        8: 2,  # Col 8 rock is at row 2
        9: 2,  # Col 9 rock is at row 2
        10: 1,  # Col 10 rock is at row 1
        11: 3,  # Col 11 rock is at row 3
        12: 2,  # Col 12 rock is at row 2 (target row is 1!)
    }
    target_row = 1
    current_col = 1
    current_row = 2

    while current_col < 12:
        next_col = current_col + 1
        rock_row = grid_obstacles[next_col]

        # 1. Compute safe moves
        safe_moves = compute_safe_moves_from_rock_row(current_row, rock_row)
        assert len(safe_moves) > 0, f"Dead end at col {current_col} -> {next_col}!"

        # 2. Select best thrust
        cmd = select_best_thrust(
            current_row=current_row,
            target_row=target_row,
            remaining_columns=12 - next_col,
            safe_commands=safe_moves,
        )

        # 3. Apply move
        if cmd == "go":
            new_row = current_row
        elif cmd == "left":
            new_row = current_row - 1
        else:
            new_row = current_row + 1

        # Assert no collision
        assert new_row != rock_row, (
            f"Collision at col {next_col}: rocket at row {new_row}, rock at {rock_row}!"
        )
        assert 1 <= new_row <= 3, (
            f"Boundary violation at col {next_col}: row {new_row}!"
        )

        current_col = next_col
        current_row = new_row

    assert current_col == 12
    # Verify rocket reached destination target row
    assert current_row == target_row


def test_select_suicide_thrust() -> None:
    # Rock dead ahead at Row 2 -> 'go' hits rock
    assert select_suicide_thrust(current_row=2, rock_row=2) == "go"
    # Rock to port side at Row 1 -> 'left' hits rock
    assert select_suicide_thrust(current_row=2, rock_row=1) == "left"
    # Rock to starboard at Row 3 -> 'right' hits rock
    assert select_suicide_thrust(current_row=2, rock_row=3) == "right"
    # Rock 2 lanes away when at top boundary -> 'left' flies out of bounds
    assert select_suicide_thrust(current_row=1, rock_row=3) == "left"
    # Rock 2 lanes away when at bottom boundary -> 'right' flies out of bounds
    assert select_suicide_thrust(current_row=3, rock_row=1) == "right"
