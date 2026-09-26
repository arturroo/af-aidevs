from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CentralaStartPayload(BaseModel):
    action: Literal["start"] = Field(
        default="start", description="Protocol action initiating radio session"
    )


class CentralaListenPayload(BaseModel):
    action: Literal["listen"] = Field(
        default="listen", description="Protocol action polling next signal"
    )


class CentralaTransmitPayload(BaseModel):
    action: Literal["transmit"] = Field(
        default="transmit", description="Protocol action submitting final findings"
    )
    cityName: str = Field(
        description="Real name of the resistance haven referred to as Syjon",
        examples=["Opalino"],
    )
    cityArea: str = Field(
        description="Mathematically rounded city area with exactly two decimal places",
        examples=["14.85"],
    )
    warehousesCount: int = Field(
        description="Total count of warehouses on Syjon", examples=[12]
    )
    phoneNumber: str = Field(
        description="Contact phone number for the city liaison",
        examples=["555-0192"],
    )


class CentralaEnvelope(BaseModel):
    apikey: str = Field(description="Personal AI_Devs API key")
    task: str = Field(default="radiomonitoring", description="Task identifier")
    answer: CentralaStartPayload | CentralaListenPayload | CentralaTransmitPayload = (
        Field(description="Action-specific answer payload")
    )


class CentralaListenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: int = Field(default=100, description="Status code from Centrala")
    message: str = Field(
        default="", description="Descriptive status message from Centrala"
    )
    transcription: str | None = Field(
        default=None,
        description="Text transcript of intercepted voice communication",
    )
    meta: str | None = Field(
        default=None,
        description="MIME-type or metadata string for binary attachments",
    )
    attachment: str | None = Field(
        default=None,
        description="Base64-encoded binary payload of intercepted signal",
    )
    filesize: int | None = Field(
        default=None, description="Size of attachment in bytes"
    )
    flag: str | None = Field(
        default=None, description="Secret or course flag returned by Centrala"
    )


class CandidateEntities(BaseModel):
    city_names: list[str] = Field(
        default_factory=list, description="Candidate city names extracted"
    )
    city_area: str | None = Field(
        default=None, description="Candidate city area extracted"
    )
    warehouses_count: int | None = Field(
        default=None, description="Candidate warehouse count extracted"
    )
    phone_numbers: list[str] = Field(
        default_factory=list, description="Candidate phone numbers extracted"
    )


class SecretClues(BaseModel):
    telegraphist_mentions: bool = Field(
        default=False,
        description="Whether Julian Tuwim or telegraphist keywords were detected",
    )
    morse_detected: bool = Field(
        default=False,
        description="Whether Morse code rhythm/pattern was detected",
    )
    raw_clue: str | None = Field(
        default=None, description="Raw context or string containing the clue"
    )
    extracted_key: str | None = Field(
        default=None, description="Decoded flag or secret key"
    )


class ObjectFinding(BaseModel):
    source_file: str = Field(
        description="Relative path to the decoded artifact in /decoded/"
    )
    mime_type: str = Field(description="Normalized MIME type of the artifact")
    summary_sentences: list[str] = Field(
        description="Exactly 3-4 dense factual sentences describing scene, OCR, metrics",
        max_length=4,
    )
    schema_or_structure: dict[str, Any] = Field(
        default_factory=dict,
        description="Table schemas, JSON keys, or Markdown TOC section titles",
    )
    candidate_entities: CandidateEntities = Field(
        default_factory=CandidateEntities,
        description="Extracted candidate parameters for Syjon",
    )
    secret_clues: SecretClues = Field(
        default_factory=SecretClues,
        description="Observations regarding Morse code or telegraphist secrets",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for this finding",
    )
    reasoning: str = Field(
        default="", description="Justification and notes on extraction"
    )


class RunTaskRequest(BaseModel):
    backend: Literal["langchain"] = Field(
        default="langchain", description="Agent backend execution framework"
    )
    session_id: str | None = Field(
        default=None, description="Optional custom session ID override"
    )
    model: str | None = Field(
        default=None,
        description="Synthesis model override (default: gemini-3.8-flash)",
    )
    enrichment_model: str | None = Field(
        default=None,
        description="Enrichment model override (default: gemini-3.5-flash-lite)",
    )
    thinking_level: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="Reflection depth level override for synthesis model",
    )
    max_iterations: int | None = Field(
        default=None, description="Maximum agent iteration ceiling"
    )


class RunTaskResponse(BaseModel):
    status: Literal["success", "error"] = Field(
        description="Overall task execution status"
    )
    session_id: str = Field(description="Session ID under which files were staged")
    city_name: str | None = Field(
        default=None, description="Identified real name of Syjon"
    )
    city_area: str | None = Field(
        default=None, description="Mathematically rounded city area (ROUND_HALF_UP)"
    )
    warehouses_count: int | None = Field(
        default=None, description="Count of warehouses"
    )
    phone_number: str | None = Field(default=None, description="Contact phone number")
    secret_flag: str | None = Field(
        default=None, description="Decoded easter egg flag if discovered"
    )
    mission_flag: str | None = Field(
        default=None, description="Mission flag returned by Centrala"
    )
    execution_time_seconds: float = Field(
        default=0.0, description="Total execution wall-clock time"
    )
    error: str | None = Field(
        default=None, description="Error message if execution failed"
    )
