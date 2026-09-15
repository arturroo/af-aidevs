import pytest
from schemas import BlockState
from services.pathfinding_service import (
    CYCLE_PERIOD,
    PathfindingService,
    predict_block_positions,
    step_single_block,
)


def test_step_single_block_cycle():
    """Verifies that a 2-cell block oscillates vertically with period 6."""
    top_row, direction = 1, "down"
    history = [(top_row, direction)]

    for _ in range(CYCLE_PERIOD):
        top_row, direction = step_single_block(top_row, direction)
        history.append((top_row, direction))

    # After 6 steps, should return to initial state
    assert history[0] == history[CYCLE_PERIOD]
    assert history == [
        (1, "down"),
        (2, "down"),
        (3, "down"),
        (4, "up"),
        (3, "up"),
        (2, "up"),
        (1, "down"),
    ]


def test_predict_block_positions():
    """Verifies forward simulation of multiple blocks."""
    blocks = {
        2: BlockState(column=2, top_row=1, direction="down"),
        4: BlockState(column=4, top_row=3, direction="down"),
    }

    step_1 = predict_block_positions(blocks, 1)
    assert step_1[2].top_row == 2
    assert step_1[2].direction == "down"
    assert step_1[4].top_row == 4
    assert step_1[4].direction == "up"

    # Step 2: Col 4 should bounce to row 3
    step_2 = predict_block_positions(blocks, 2)
    assert step_2[4].top_row == 3
    assert step_2[4].direction == "up"


def test_is_floor_blocked():
    """Verifies detection of obstacle on the floor (Row 5)."""
    blocks = {
        2: BlockState(column=2, top_row=4, direction="up"),
        3: BlockState(column=3, top_row=2, direction="down"),
    }
    assert PathfindingService.is_floor_blocked(blocks, 2) is True
    assert PathfindingService.is_floor_blocked(blocks, 3) is False
    assert PathfindingService.is_floor_blocked(blocks, 5) is False


def test_find_shortest_safe_path_clear_corridor():
    """In an empty chamber, optimal path is 6 straight 'right' moves."""
    blocks = {}
    path = PathfindingService.find_shortest_safe_path(
        start_col=1, target_col=7, current_blocks=blocks
    )
    assert path == ["right"] * 6


def test_find_shortest_safe_path_with_descending_block():
    """If Column 2 block is descending to floor at t=1, robot must wait before advancing."""
    # Col 2 is at row 3 moving down. At t=1, it will be at row 4 (blocking floor!).
    # If robot moves 'right' at t=0, it lands in Col 2 at t=1 -> crushed!
    # Robot should wait at Col 1.
    blocks = {
        2: BlockState(column=2, top_row=3, direction="down"),
    }
    path = PathfindingService.find_shortest_safe_path(
        start_col=1, target_col=7, current_blocks=blocks
    )
    assert path is not None
    # First move must NOT be right (which causes collision at t=1)
    assert path[0] == "wait"
    # Destination must be reached
    # Verify no collision throughout path execution
    sim_blocks = blocks
    cur_col = 1
    for cmd in path:
        sim_blocks = predict_block_positions(sim_blocks, 1)
        if cmd == "right":
            cur_col += 1
        elif cmd == "left":
            cur_col -= 1
        # Check floor safety
        assert not PathfindingService.is_floor_blocked(sim_blocks, cur_col)
    assert cur_col == 7


def test_parse_blocks_from_map():
    """Verifies ASCII map parsing into BlockState objects."""
    raw_map = [
        ".......",  # Row 1
        ".B.....",  # Row 2 (Col 2 has B)
        ".B.....",  # Row 3 (Col 2 has B)
        ".......",  # Row 4
        "P.....G",  # Row 5 (Floor)
    ]
    parsed = PathfindingService.parse_blocks_from_map(raw_map)
    assert 2 in parsed
    assert parsed[2].top_row == 2
    assert parsed[2].column == 2
