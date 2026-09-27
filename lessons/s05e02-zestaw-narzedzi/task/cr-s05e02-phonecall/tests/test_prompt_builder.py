from schemas import DialogueState
from services.prompt_builder import STATIC_PERSONA_AND_RULES, PromptBuilder


def test_prompt_builder_structure():
    state = DialogueState(selected_evacuation_road="RD472")
    state.conversation_history.append("Tymon: Dzień dobry.")
    state.conversation_history.append("Operator: Słucham.")

    prompt = PromptBuilder.build_speech_prompt(
        state=state,
        objective="REQUEST_MONITORING_DEACTIVATION",
        last_operator_utterance="Słucham.",
    )

    # 1. Static persona at top
    assert prompt.startswith(STATIC_PERSONA_AND_RULES)

    # 2. History in middle
    assert "HISTORIA ROZMOWY:" in prompt
    assert "- Tymon: Dzień dobry." in prompt
    assert "- Operator: Słucham." in prompt

    # 3. Recency attention at bottom
    assert 'OSTATNIA WYPOWIEDŹ OPERATORA:\n"Słucham."' in prompt
    assert "CEL TEJ TURY: Poproś operatora o wyłączenie monitoringu" in prompt
    assert "RD472" in prompt
    assert "<speak>" in prompt
