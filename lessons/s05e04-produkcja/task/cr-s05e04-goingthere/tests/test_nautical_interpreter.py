"""Unit tests for nautical hint resolution and safe move computation."""

from services.navigator_service import (
    compute_safe_moves_from_rock_row,
    heuristic_nautical_fallback,
)


def test_safe_moves_when_rock_is_dead_ahead_middle_row() -> None:
    # Rocket at Row 2, Rock at Row 2, no current column rock
    # 'go' hits rock -> blocked
    # 'left' moves to Row 1 -> safe
    # 'right' moves to Row 3 -> safe
    moves = compute_safe_moves_from_rock_row(current_row=2, rock_row=2)
    assert set(moves) == {"left", "right"}


def test_safe_moves_blocks_corner_cutting_rock_in_current_column() -> None:
    # Rocket at Row 2, Rock ahead at Row 2.
    # Current column rock at Row 1.
    # 'left' is blocked by current rock at Row 1!
    # Only 'right' is safe.
    moves = compute_safe_moves_from_rock_row(
        current_row=2, rock_row=2, current_col_rock_row=1
    )
    assert moves == ["right"]

    # Current column rock at Row 3.
    # 'right' is blocked by current rock at Row 3!
    # Only 'left' is safe.
    moves_left = compute_safe_moves_from_rock_row(
        current_row=2, rock_row=2, current_col_rock_row=3
    )
    assert moves_left == ["left"]


def test_safe_moves_at_top_boundary() -> None:
    # Rocket at Row 1, Rock at Row 1
    # 'left' is out of bounds (< 1) -> blocked
    # 'go' hits rock at Row 1 -> blocked
    # 'right' moves to Row 2 -> safe
    moves = compute_safe_moves_from_rock_row(current_row=1, rock_row=1)
    assert moves == ["right"]


def test_safe_moves_at_bottom_boundary() -> None:
    # Rocket at Row 3, Rock at Row 3
    # 'right' is out of bounds (> 3) -> blocked
    # 'go' hits rock at Row 3 -> blocked
    # 'left' moves to Row 2 -> safe
    moves = compute_safe_moves_from_rock_row(current_row=3, rock_row=3)
    assert moves == ["left"]


def test_safe_moves_when_rock_is_on_port_side() -> None:
    # Rocket at Row 2, Rock at Row 1 (Port)
    # 'left' moves to Row 1 -> hits rock -> blocked
    # 'go' moves to Row 2 -> safe
    # 'right' moves to Row 3 -> safe
    moves = compute_safe_moves_from_rock_row(current_row=2, rock_row=1)
    assert set(moves) == {"go", "right"}


def test_safe_moves_when_rock_is_on_starboard_side() -> None:
    # Rocket at Row 2, Rock at Row 3 (Starboard)
    # 'right' moves to Row 3 -> hits rock -> blocked
    # 'go' moves to Row 2 -> safe
    # 'left' moves to Row 1 -> safe
    moves = compute_safe_moves_from_rock_row(current_row=2, rock_row=3)
    assert set(moves) == {"go", "left"}


def test_heuristic_nautical_fallback_port() -> None:
    extraction = heuristic_nautical_fallback(
        "Beware of dangerous shoals on the port side", current_row=2
    )
    assert extraction.rock_relative_direction == "left"
    assert extraction.rock_absolute_row == 1
    assert set(extraction.safe_commands) == {"go", "right"}


def test_heuristic_nautical_fallback_starboard() -> None:
    extraction = heuristic_nautical_fallback(
        "Reef spotted to starboard, proceed with caution", current_row=2
    )
    assert extraction.rock_relative_direction == "right"
    assert extraction.rock_absolute_row == 3
    assert set(extraction.safe_commands) == {"go", "left"}


def test_heuristic_nautical_fallback_dead_ahead() -> None:
    extraction = heuristic_nautical_fallback(
        "Massive rock formation lying dead ahead", current_row=2
    )
    assert extraction.rock_relative_direction == "ahead"
    assert extraction.rock_absolute_row == 2
    assert set(extraction.safe_commands) == {"left", "right"}


def test_format_columns_history() -> None:
    from schemas import GameColumn
    from services.navigator_service import format_columns_history

    empty_res = format_columns_history(None)
    assert "No prior columns" in empty_res

    history = {
        1: GameColumn(column=1, your_row=2, stone_row=3, free_rows=[1, 2]),
        2: GameColumn(column=2, your_row=1, stone_row=2, free_rows=[1, 3]),
    }
    formatted = format_columns_history(history)
    assert (
        "- Column 1: Rocket was at Row 2 | Rock at Row 3 | Free Rows [1, 2]"
        in formatted
    )
    assert (
        "- Column 2: Rocket was at Row 1 | Rock at Row 2 | Free Rows [1, 3]"
        in formatted
    )
