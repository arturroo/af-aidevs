import logging

from schemas import DialogueState, TurnObjective

logger = logging.getLogger("services.policy_engine")


class PolicyEngine:
    """Deterministic decision engine mapping DialogueState to TurnObjective."""

    @staticmethod
    def determine_next_objective(state: DialogueState) -> TurnObjective:
        # Priority 1: Mandatory Opening
        # Must bundle: introduce Tymon Gajewski + ask 3 roads + transport to Zygfryd's base
        if not state.opening_message_sent:
            logger.info("Policy: Setting objective -> SEND_OPENING_MESSAGE")
            return "SEND_OPENING_MESSAGE"

        # Priority 2: Clear Authorization Challenge Immediately
        if state.auth_requested and not state.auth_code_provided:
            logger.info("Policy: Setting objective -> ANSWER_AUTH_CHALLENGE")
            return "ANSWER_AUTH_CHALLENGE"

        # Priority 3: De-escalate Suspicion / Cover Story
        if state.operator_suspicious and not state.food_legend_used:
            logger.info("Policy: Setting objective -> EXPLAIN_FOOD_LEGEND")
            return "EXPLAIN_FOOD_LEGEND"

        # Priority 4: Inquire / Clarify road statuses if safe road not yet identified
        if state.selected_evacuation_road is None:
            logger.info("Policy: Setting objective -> INQUIRE_ROAD_STATUSES")
            return "INQUIRE_ROAD_STATUSES"

        # Priority 5: Request Monitoring Deactivation on Confirmed Safe Road
        if not state.monitoring_deactivation_requested:
            logger.info(
                f"Policy: Setting objective -> REQUEST_MONITORING_DEACTIVATION for {state.selected_evacuation_road}"
            )
            return "REQUEST_MONITORING_DEACTIVATION"

        # Priority 6: Await Confirmation & Terminal Flag Extraction
        logger.info("Policy: Setting objective -> AWAIT_CONFIRMATION_AND_FLAG")
        return "AWAIT_CONFIRMATION_AND_FLAG"
