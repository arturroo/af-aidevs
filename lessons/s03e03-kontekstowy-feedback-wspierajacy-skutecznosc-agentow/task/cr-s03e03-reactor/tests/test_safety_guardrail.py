import pytest
from schemas import BlockState
from services.safety_guardrail import SafetyGuardrailService


def test_guardrail_allows_safe_move():
    """Allows moving to an empty column."""
    blocks = {
        2: BlockState(column=2, top_row=1, direction="down"),  # At t=1 will be at row 2
    }
    is_safe, expl, target = SafetyGuardrailService.validate_command(
        current_col=1, command="right", current_blocks=blocks
    )
    assert is_safe is True
    assert target == 2


def test_guardrail_rejects_suicidal_move():
    """Rejects stepping into a column where block descends to Row 5 at t=1."""
    blocks = {
        2: BlockState(column=2, top_row=3, direction="down"),  # At t=1 will be at row 4 (covers row 5)
    }
    is_safe, expl, target = SafetyGuardrailService.validate_command(
        current_col=1, command="right", current_blocks=blocks
    )
    assert is_safe is False
    assert "Collision Hazard" in expl
    assert target == 2


def test_guardrail_rejects_suicidal_wait():
    """Rejects waiting in a column if current column block will crush robot at t=1."""
    blocks = {
        3: BlockState(column=3, top_row=3, direction="down"),  # At t=1 will be at row 4
    }
    is_safe, expl, target = SafetyGuardrailService.validate_command(
        current_col=3, command="wait", current_blocks=blocks
    )
    assert is_safe is False
    assert "Collision Hazard" in expl
    assert target == 3


def test_guardrail_rejects_out_of_bounds():
    """Rejects moving left from Column 1 or right from Column 7."""
    is_safe, expl, _ = SafetyGuardrailService.validate_command(
        current_col=1, command="left", current_blocks={}
    )
    assert is_safe is False
    assert "Boundary Violation" in expl

    is_safe, expl, _ = SafetyGuardrailService.validate_command(
        current_col=7, command="right", current_blocks={}
    )
    assert is_safe is False
    assert "Boundary Violation" in expl


def test_guardrail_allows_administrative_commands():
    """Allows start and reset unconditionally."""
    is_safe, expl, _ = SafetyGuardrailService.validate_command(
        current_col=1, command="start", current_blocks={}
    )
    assert is_safe is True

    is_safe, expl, _ = SafetyGuardrailService.validate_command(
        current_col=3, command="reset", current_blocks={}
    )
    assert is_safe is True
