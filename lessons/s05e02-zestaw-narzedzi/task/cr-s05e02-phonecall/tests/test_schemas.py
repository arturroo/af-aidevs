from schemas import (
    DialogueState,
    OperatorTurnAnalysis,
    RunTaskRequest,
    create_default_roads,
)


def test_default_roads_isolation():
    roads_1 = create_default_roads()
    roads_2 = create_default_roads()
    roads_1["RD224"].status = "passable"
    assert roads_2["RD224"].status == "unknown"


def test_dialogue_state_mutable_isolation():
    state_a = DialogueState()
    state_b = DialogueState()
    state_a.roads["RD472"].status = "passable"
    state_a.conversation_history.append("Turn 1")

    assert state_b.roads["RD472"].status == "unknown"
    assert len(state_b.conversation_history) == 0


def test_operator_turn_analysis_defaults():
    analysis = OperatorTurnAnalysis(
        operator_transcript="RD472 jest czysta.",
        overall_sentiment="cooperative",
        suspicion_level="low",
        reasoning="Operator is calm and informative",
    )
    assert analysis.call_burned is False
    assert analysis.auth_requested is False
    assert analysis.overall_sentiment == "cooperative"


def test_run_task_request_overrides():
    req = RunTaskRequest(
        max_iterations=20,
        voice_name="pl-PL-Wavenet-B",
        speaking_rate=1.10,
        max_restarts=3,
    )
    assert req.max_iterations == 20
    assert req.voice_name == "pl-PL-Wavenet-B"
    assert req.speaking_rate == 1.10
    assert req.max_restarts == 3
