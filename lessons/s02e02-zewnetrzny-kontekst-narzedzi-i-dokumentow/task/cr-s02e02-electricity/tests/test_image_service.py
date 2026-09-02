from pathlib import Path
import pytest
import numpy as np
from PIL import Image
from services.image_service import crop_tiles, extract_tile_pinout, extract_board_pinouts, load_image
from services.puzzle_service import calculate_tile_rotation_delta

SOLVED_IMAGE_PATH = Path(__file__).parent.parent.parent.parent / "solved_electricity.png"


def test_crop_tiles():
    """Verify that 3x3 slicing returns 9 valid PIL images."""
    assert SOLVED_IMAGE_PATH.exists(), f"Reference image missing at {SOLVED_IMAGE_PATH}"
    tiles = crop_tiles(SOLVED_IMAGE_PATH)
    assert len(tiles) == 3
    assert all(len(row) == 3 for row in tiles)
    assert tiles[0][0].size == (95, 95)


def test_solved_board_pinouts():
    """Verify that pinouts extracted from solved_electricity.png match expected ground truth."""
    board_pinouts, confidences = extract_board_pinouts(SOLVED_IMAGE_PATH)

    # 1x1: corner turning Right to Bottom
    assert board_pinouts[0][0].top is False
    assert board_pinouts[0][0].right is True
    assert board_pinouts[0][0].bottom is True
    assert board_pinouts[0][0].left is False

    # 2x1: vertical line Top to Bottom
    assert board_pinouts[1][0].top is True
    assert board_pinouts[1][0].bottom is True
    assert board_pinouts[1][0].left is False
    assert board_pinouts[1][0].right is False

    # 3x1: emergency source T-junction (Left, Top, Right)
    assert board_pinouts[2][0].left is True
    assert board_pinouts[2][0].top is True
    assert board_pinouts[2][0].right is True
    assert board_pinouts[2][0].bottom is False

    # All tiles must have high confidence
    for row in confidences:
        for conf in row:
            assert conf >= 0.85


def test_synthetic_tile_rotations():
    """
    Synthetic TDD Test:
    Take each tile from solved_electricity.png, artificially rotate it by 90°, 180°, 270° CW,
    and assert that edge sampling and delta calculation recovers the exact rotation steps!
    """
    tiles = crop_tiles(SOLVED_IMAGE_PATH)
    board_target_pinouts, _ = extract_board_pinouts(SOLVED_IMAGE_PATH)

    for r in range(3):
        for c in range(3):
            original_tile = tiles[r][c]
            target_pinout = board_target_pinouts[r][c]

            for expected_steps_cw in [0, 1, 2, 3]:
                # In PIL, rotate(degrees) rotates CCW, so rotate(-90 * steps) rotates CW
                # To simulate an image that needs 'expected_steps_cw' to match target:
                # The scrambled tile was rotated CCW by expected_steps_cw
                scrambled_tile = original_tile.rotate(90 * expected_steps_cw)

                scrambled_pinout, pin_conf = extract_tile_pinout(scrambled_tile)
                computed_steps, match_conf = calculate_tile_rotation_delta(scrambled_pinout, target_pinout)

                assert match_conf == 1.0, f"Failed match on tile {r+1}x{c+1} with {expected_steps_cw} rotations"
                
                # Check modulo rotation equivalence (handling 180° symmetric straight lines)
                is_symmetric_line = (target_pinout.top == target_pinout.bottom) and (target_pinout.left == target_pinout.right)
                if is_symmetric_line:
                    assert computed_steps % 2 == expected_steps_cw % 2
                else:
                    assert computed_steps == expected_steps_cw


def test_live_board_diagnostics():
    """Diagnoses edge patch extraction on solved vs live board and tests verification."""
    import httpx
    import config
    from services.puzzle_service import compute_board_rotations, generate_rotation_commands

    api_key = config.AIDEVS_API_KEY or "9b3cbf77-af69-4a90-aaa8-d3a9592767ee"
    reset_url = f"https://hub.ag3nts.org/data/{api_key}/electricity.png?reset=1"
    verify_url = "https://hub.ag3nts.org/verify"

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(reset_url)
        resp.raise_for_status()
        curr_bytes = resp.content

        live_pins, live_confs = extract_board_pinouts(curr_bytes)
        solved_pins, solved_confs = extract_board_pinouts(SOLVED_IMAGE_PATH)

        solver = compute_board_rotations(live_pins, solved_pins, live_confs)
        cmds = generate_rotation_commands(solver.rotations)
        print("\n[DIAGNOSTIC] Rotations matrix:", solver.rotations)
        print("[DIAGNOSTIC] Commands:", [(c.tile_id, c.steps_cw) for c in cmds])

        last_resp = None
        for cmd in cmds:
            for _ in range(cmd.steps_cw):
                payload = {"apikey": api_key, "task": "electricity", "answer": {"rotate": cmd.tile_id}}
                r = client.post(verify_url, json=payload)
                print(f"[DIAGNOSTIC] Rotate {cmd.tile_id} -> {r.status_code} {r.text}")
                last_resp = r.json()

        assert last_resp is not None
        assert last_resp.get("code") == 0, f"Expected code 0 with flag, got {last_resp}"
        assert "{FLG:" in last_resp.get("message", ""), f"Flag not in message: {last_resp}"

