"""Pydantic schemas and contract definitions for cr-s05e03-shellaccess."""

from typing import Literal

from pydantic import BaseModel, Field


class RunTaskRequest(BaseModel):
    """Execution request payload for the Cloud Run /run endpoint and CLI."""

    backend: Literal["langchain", "adk"] = Field(
        default="langchain",
        description="Agent backend orchestration framework",
        examples=["langchain", "adk"],
    )
    session_id: str | None = Field(
        default=None,
        description="Session identifier for audit tracing and workspace isolation",
        examples=["session-s05e03-abc1234"],
    )
    model: str | None = Field(
        default=None,
        description="Dynamic LLM model override for evaluation and testing",
        examples=["gemini-3.8-flash"],
    )
    max_iterations: int = Field(
        default=30,
        description="Maximum turns in the ReAct exploration loop",
        examples=[30],
    )
    thinking_level: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="Reasoning effort level for Gemini models",
        examples=["low"],
    )


class RemoteCommandPayload(BaseModel):
    """Payload representing a command to execute on Centrala's remote host."""

    cmd: str = Field(
        ...,
        description="UNIX shell command to execute on the remote Linux host",
        examples=["ls -la /data", "grep -i rafal /data/archive.log | head -n 5"],
    )


class CentralaVerifyRequest(BaseModel):
    """Request envelope sent to Centrala's verification endpoint."""

    apikey: str = Field(..., description="Course API key for authentication")
    task: str = Field(default="shellaccess", description="Task identifier")
    answer: RemoteCommandPayload = Field(
        ..., description="Command payload for shell execution"
    )


class CentralaVerifyResponse(BaseModel):
    """Response returned by Centrala after command execution."""

    code: int = Field(
        ..., description="Status code from Centrala (0 for success, -1 for error)"
    )
    message: str = Field(
        ..., description="Stdout, stderr, or system message returned by Centrala"
    )
    output: str | None = Field(
        default=None, description="Standard output returned by Centrala remote command"
    )


class RafalDiscoveryExtraction(BaseModel):
    """Structured extraction of Rafał's body discovery from the logs."""

    discovery_date: str = Field(
        ...,
        description="Raw ISO-8601 date when Rafał's body was discovered (YYYY-MM-DD)",
        examples=["2024-03-01"],
    )
    city: str = Field(
        ...,
        description="Name of the city where Rafał was discovered",
        examples=["Grudziadz"],
    )
    latitude: float = Field(
        ...,
        description="Geographical latitude of the discovery location",
        examples=[53.4837],
    )
    longitude: float = Field(
        ...,
        description="Geographical longitude of the discovery location",
        examples=[18.7533],
    )
    reasoning: str = Field(
        default="",
        description="Chain-of-thought rationale explaining how and where the data was located in the logs",
        examples=[
            "Discovered in /data/incidents.log line 42 mentioning coroner report for Rafal."
        ],
    )


class RendezvousPayload(BaseModel):
    """Final JSON rendezvous coordinates sent to Centrala."""

    date: str = Field(
        ...,
        description="Rendezvous date exactly ONE DAY BEFORE discovery (YYYY-MM-DD)",
        examples=["2024-02-29"],
    )
    city: str = Field(
        ...,
        description="Target rendezvous city name",
        examples=["Grudziadz"],
    )
    longitude: float = Field(
        ...,
        description="Longitude coordinate",
        examples=[18.7533],
    )
    latitude: float = Field(
        ...,
        description="Latitude coordinate",
        examples=[53.4837],
    )


class RunTaskResponse(BaseModel):
    """Final response returned from Cloud Run /run endpoint."""

    session_id: str = Field(
        ...,
        description="Session identifier associated with this execution run",
        examples=["session-s05e03-abc1234"],
    )
    status: Literal["completed", "failed"] = Field(
        ...,
        description="Final status of task execution",
        examples=["completed"],
    )
    flag: str | None = Field(
        default=None,
        description="Extracted course flag token if successfully verified",
        examples=["{FLG:...}"],
    )
    rendezvous: RendezvousPayload | None = Field(
        default=None,
        description="Validated rendezvous parameters submitted to Centrala",
    )
    total_turns: int = Field(
        ...,
        description="Total turns/commands executed during the session",
        examples=[6],
    )
    execution_time_seconds: float = Field(
        ...,
        description="Total duration of the execution run in seconds",
        examples=[8.42],
    )
    error: str | None = Field(
        default=None,
        description="Error description if status is failed",
    )
