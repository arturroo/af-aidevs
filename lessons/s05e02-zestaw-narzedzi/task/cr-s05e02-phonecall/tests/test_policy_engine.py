from schemas import DialogueState
from services.policy_engine import PolicyEngine


def test_priority_1_opening_message():
    state = DialogueState(opening_message_sent=False)
    objective = PolicyEngine.determine_next_objective(state)
    assert objective == "SEND_OPENING_MESSAGE"


def test_priority_2_auth_challenge():
    state = DialogueState(
        opening_message_sent=True,
        auth_requested=True,
        auth_code_provided=False,
    )
    objective = PolicyEngine.determine_next_objective(state)
    assert objective == "ANSWER_AUTH_CHALLENGE"


def test_priority_3_deescalate_suspicion():
    state = DialogueState(
        opening_message_sent=True,
        auth_requested=False,
        operator_suspicious=True,
        food_legend_used=False,
    )
    objective = PolicyEngine.determine_next_objective(state)
    assert objective == "EXPLAIN_FOOD_LEGEND"


def test_priority_4_inquire_road_statuses():
    state = DialogueState(
        opening_message_sent=True,
        selected_evacuation_road=None,
    )
    objective = PolicyEngine.determine_next_objective(state)
    assert objective == "INQUIRE_ROAD_STATUSES"


def test_priority_5_request_monitoring_deactivation():
    state = DialogueState(
        opening_message_sent=True,
        selected_evacuation_road="RD472",
        monitoring_deactivation_requested=False,
    )
    objective = PolicyEngine.determine_next_objective(state)
    assert objective == "REQUEST_MONITORING_DEACTIVATION"


def test_priority_6_await_confirmation():
    state = DialogueState(
        opening_message_sent=True,
        selected_evacuation_road="RD472",
        monitoring_deactivation_requested=True,
    )
    objective = PolicyEngine.determine_next_objective(state)
    assert objective == "AWAIT_CONFIRMATION_AND_FLAG"
