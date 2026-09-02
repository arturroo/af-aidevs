import pytest
from af_aidevs.schemas.vision import TilePinout
from services.puzzle_service import (
    rotate_pinout_cw,
    calculate_tile_rotation_delta,
    compute_board_rotations,
    generate_rotation_commands,
)


def test_rotate_pinout_cw():
    """Verify that rotating (top, right, bottom, left) 1 step CW shifts values correctly."""
    # Start with wire pointing Top (True, False, False, False)
    pins = TilePinout(top=True, right=False, bottom=False, left=False)

    rot1 = rotate_pinout_cw(pins, steps=1)
    assert rot1 == TilePinout(top=False, right=True, bottom=False, left=False)

    rot2 = rotate_pinout_cw(pins, steps=2)
    assert rot2 == TilePinout(top=False, right=False, bottom=True, left=False)

    rot3 = rotate_pinout_cw(pins, steps=3)
    assert rot3 == TilePinout(top=False, right=False, bottom=False, left=True)

    rot4 = rotate_pinout_cw(pins, steps=4)
    assert rot4 == pins


def test_calculate_tile_rotation_delta():
    """Verify delta calculation between different tile pinouts."""
    curr = TilePinout(top=True, right=True, bottom=False, left=False)  # corner Top-Right
    targ = TilePinout(top=False, right=True, bottom=True, left=False)  # corner Right-Bottom

    steps, conf = calculate_tile_rotation_delta(curr, targ)
    assert steps == 1
    assert conf == 1.0


def test_generate_rotation_commands():
    """Verify that matrix with non-zero rotations produces correct command objects."""
    rot_matrix = [
        [0, 1, 0],
        [2, 0, 3],
        [0, 0, 0],
    ]
    cmds = generate_rotation_commands(rot_matrix)
    assert len(cmds) == 3
    assert cmds[0].tile_id == "1x2" and cmds[0].steps_cw == 1
    assert cmds[1].tile_id == "2x1" and cmds[1].steps_cw == 2
    assert cmds[2].tile_id == "2x3" and cmds[2].steps_cw == 3
