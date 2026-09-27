from typing import Literal

from pydantic import BaseModel, Field

RoadCode = Literal["RD224", "RD472", "RD820"]
RoadStatus = Literal["passable", "blocked", "contaminated", "unknown"]
MonitoringState = Literal["active", "disabled", "pending_auth", "refused", "unknown"]
TurnObjective = Literal[
    "SEND_OPENING_MESSAGE",
    "INQUIRE_ROAD_STATUSES",
    "EXPLAIN_FOOD_LEGEND",
    "ANSWER_AUTH_CHALLENGE",
    "REQUEST_MONITORING_DEACTIVATION",
    "AWAIT_CONFIRMATION_AND_FLAG",
]


class RoadAssessment(BaseModel):
    status: RoadStatus = Field(default="unknown", description="Przejezdność drogi")
    monitoring: MonitoringState = Field(
        default="active", description="Stan monitoringu na trasie"
    )
    operator_justification: str | None = Field(
        default=None, description="Uzasadnienie operatora"
    )


def create_default_roads() -> dict[RoadCode, RoadAssessment]:
    return {
        "RD224": RoadAssessment(status="unknown", monitoring="active"),
        "RD472": RoadAssessment(status="unknown", monitoring="active"),
        "RD820": RoadAssessment(status="unknown", monitoring="active"),
    }


class SentenceAnalysis(BaseModel):
    sentence: str = Field(description="Sentence text")
    sentiment: Literal["positive", "neutral", "negative", "sarcastic"] = Field(
        description="Sentiment of this specific sentence"
    )
    is_irony: bool = Field(
        default=False, description="True if sentence expresses irony"
    )
    is_humor: bool = Field(
        default=False, description="True if sentence contains humor/joke"
    )
    topic: Literal[
        "mission_logistics", "small_talk", "security_auth", "weather_other"
    ] = Field(description="Topical classification of the sentence")


class RoadObservation(BaseModel):
    road: RoadCode = Field(description="Road identifier: RD224, RD472, or RD820")
    status: RoadStatus = Field(
        description="Road status: passable, blocked, contaminated, unknown"
    )
    justification: str = Field(
        default="", description="Operator's justification or explanation"
    )


class OperatorTurnAnalysis(BaseModel):
    operator_transcript: str = Field(
        description="Verbatim Polish transcript of operator speech"
    )
    sentence_analyses: list[SentenceAnalysis] = Field(
        default_factory=list, description="Sentence-level behavioral analysis"
    )
    overall_sentiment: Literal["cooperative", "neutral", "suspicious", "hostile"] = (
        Field(description="Overall conversational tone")
    )
    suspicion_level: Literal["low", "medium", "high", "critical"] = Field(
        description="Level of operator suspicion"
    )
    auth_requested: bool = Field(
        default=False,
        description="True if operator challenged for clearance/password/identity",
    )
    monitoring_disabled_confirmed: bool = Field(
        default=False,
        description="True if operator confirmed monitoring is deactivated",
    )
    roads: list[RoadObservation] = Field(
        default_factory=list,
        description="Observations for each road mentioned by operator",
    )
    call_burned: bool = Field(
        default=False,
        description=(
            "Set to True ONLY if operator EXPLICITLY terminated conversation (hung up, sounded alarm, "
            "screamed spy/imposter, or permanently refused further interaction). Hesitation, gruffness, "
            "demanding the BARBAKAN password, or asking why monitoring must be disabled are strictly False!"
        ),
    )

    @property
    def road_statuses(self) -> dict[RoadCode, RoadStatus]:
        return {obs.road: obs.status for obs in self.roads}

    @property
    def operator_justifications(self) -> dict[RoadCode, str]:
        return {obs.road: obs.justification for obs in self.roads}

    call_burned_reason: str | None = Field(
        default=None, description="Reason why call was burned if applicable"
    )
    reasoning: str = Field(
        description="Chain of thought explaining deductions and road statuses"
    )


class DialogueState(BaseModel):
    # Milestone 1: Opening
    opening_message_sent: bool = Field(
        default=False,
        description="Whether Tymon Gajewski + 3 roads + Zygfryd base transport was sent in Turn 1",
    )
    # Milestone 2: Route evaluation
    roads: dict[RoadCode, RoadAssessment] = Field(default_factory=create_default_roads)
    selected_evacuation_road: RoadCode | None = Field(
        default=None, description="Identified safe passable road to Syjon"
    )

    # Milestone 3: Authorization
    auth_requested: bool = Field(
        default=False, description="Whether operator challenged for password"
    )
    auth_code_provided: bool = Field(
        default=False, description="Whether secret code BARBAKAN was provided"
    )

    # Milestone 4: Monitoring deactivation
    monitoring_deactivation_requested: bool = Field(
        default=False,
        description="Whether monitoring deactivation was requested on selected road",
    )
    monitoring_deactivation_confirmed: bool = Field(
        default=False,
        description="Whether operator confirmed monitoring deactivation",
    )

    # Milestone 5: Suspicion & Cover story
    operator_suspicious: bool = Field(
        default=False, description="Whether operator shows elevated suspicion"
    )
    food_legend_used: bool = Field(
        default=False, description="Whether food transport cover story was delivered"
    )

    # Safety & Telemetry
    call_burned: bool = Field(
        default=False, description="Whether conversation was terminated/burned"
    )
    turn_count: int = Field(default=0, description="Completed turns count")
    mission_flag: str | None = Field(
        default=None, description="Extracted mission flag {FLG:...}"
    )
    conversation_history: list[str] = Field(
        default_factory=list, description="Logged dialogue turns history"
    )


class RunTaskRequest(BaseModel):
    backend: Literal["langchain", "adk"] = Field(
        default="langchain", description="Agent orchestrator backend"
    )
    session_id: str | None = Field(
        default=None, description="Unique session identifier for audit"
    )
    model: str | None = Field(
        default=None, description="Dynamic model override (e.g. gemini-3.8-flash)"
    )
    thinking_level: Literal["low", "medium", "high"] | None = Field(
        default=None, description="Dynamic thinking level override"
    )
    max_iterations: int = Field(
        default=15, description="Max conversation turns before timeout"
    )
    voice_name: str = Field(
        default="pl-PL-Chirp3-HD-Fenrir", description="TTS voice identifier"
    )
    speaking_rate: float = Field(
        default=1.0,
        description="TTS speaking rate (1.0 is natural conversational pace)",
    )
    max_restarts: int = Field(
        default=2, description="Max session restarts if call gets burned"
    )


class RunTaskResponse(BaseModel):
    status: Literal["SUCCESS", "FAILED"] = Field(
        description="Execution status of the task"
    )
    session_id: str = Field(description="Session identifier")
    turns_completed: int = Field(description="Total conversational turns executed")
    restarts_used: int = Field(description="Number of session restarts used")
    selected_road: RoadCode | None = Field(
        default=None, description="Chosen evacuation route to Syjon"
    )
    monitoring_disabled: bool = Field(
        description="Whether monitoring was successfully disabled"
    )
    flag: str | None = Field(default=None, description="Course flag if acquired")
    error: str | None = Field(default=None, description="Error message if failed")
    reasoning: str = Field(default="", description="Summary of conversation execution")
