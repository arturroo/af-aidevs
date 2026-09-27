from schemas import OperatorTurnAnalysis


def test_benign_hesitation_is_not_call_burned():
    analysis = OperatorTurnAnalysis(
        operator_transcript="Hmm, no nie wiem, a dlaczego właściwie pytasz o ten monitoring?",
        overall_sentiment="suspicious",
        suspicion_level="medium",
        call_burned=False,
        reasoning="Operator is questioning rationale but has not terminated the call",
    )
    assert analysis.call_burned is False
    assert analysis.suspicion_level == "medium"


def test_explicit_termination_is_call_burned():
    analysis = OperatorTurnAnalysis(
        operator_transcript="Alarm! To jest szpieg! Rozłączam się!",
        overall_sentiment="hostile",
        suspicion_level="critical",
        call_burned=True,
        call_burned_reason="Operator sounded alarm and disconnected",
        reasoning="Explicit hangup and alarm detected",
    )
    assert analysis.call_burned is True
    assert analysis.call_burned_reason == "Operator sounded alarm and disconnected"
