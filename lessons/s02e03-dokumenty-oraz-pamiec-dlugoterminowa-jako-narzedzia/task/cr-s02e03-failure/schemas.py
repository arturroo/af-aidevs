from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# --- Agent Communication Pattern ---

class AgentResponse(BaseModel):
    """Standardized top-level agent communication schema."""
    reasoning: str = Field(
        ...,
        description="Justification and step-by-step reasoning leading to the answer.",
        examples=["All high-severity telemetry events between 06:00 and 22:00 were identified and condensed to 1380 tokens."]
    )
    answer: str = Field(
        ...,
        description="Final answer or result produced by the agent.",
        examples=["Task failure solved. Flag retrieved: {FLG:...}"]
    )


# --- Microservice API Schemas ---

class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = Field(..., description="Service status indicator", examples=["ok"])
    service: str = Field(..., description="Microservice identifier", examples=["cr-s02e03-failure"])
    version: str = Field(..., description="Application semantic version", examples=["0.1.0"])


class RunTaskRequest(BaseModel):
    """Request payload to initiate failure log compression and verification."""
    backend: str = Field(
        default="langchain",
        description="LLM execution backend framework: 'langchain' or 'genai'",
        examples=["langchain"]
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional pre-generated session ID. If omitted, a standardized ID will be generated.",
        examples=["s02e03_langchain_20260904_221500"]
    )
    max_iterations: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of feedback refinement iterations with Centrala.",
        examples=[5]
    )


class RunTaskResponse(BaseModel):
    """Response returned upon completing or processing the failure task."""
    status: str = Field(..., description="Task resolution status ('success', 'partial', or 'failed')", examples=["success"])
    session_id: str = Field(..., description="Standardized session ID used for BigQuery audit tracing", examples=["s02e03_langchain_20260904_221500"])
    flag: Optional[str] = Field(default=None, description="Course completion flag received from Centrala", examples=["{FLG:...}"])
    token_count: int = Field(..., description="Total token count of the submitted condensed log", examples=[1380])
    iterations: int = Field(..., description="Number of feedback remediation rounds executed", examples=[2])
    condensed_logs_sample: str = Field(..., description="Preview sample of the condensed log text", examples=["[2026-02-26 06:04] [CRIT] ECCS8 runaway outlet temp..."])
    notes_file: str = Field(default="run_notes.txt", description="Filename of the audit summary in session workspace", examples=["run_notes.txt"])


# --- Tool Input & Response Contracts (Google AIP Aligned) ---

class DownloadLogInput(BaseModel):
    """Input contract for staging the remote failure log into the session workspace."""
    reasoning: str = Field(
        ...,
        description="Mandatory justification explaining why the remote log must be fetched into workspace.",
        examples=["Downloading raw failure.log via cr-mcp-web-gateway into workspace before beginning in-memory analysis."]
    )
    url: Optional[str] = Field(
        default=None,
        description="Optional custom URL for the log file. Defaults to authoritative URL from configuration.",
        examples=["https://hub.ag3nts.org/data/secret-key/failure.log"]
    )
    output_path: str = Field(
        default="failure.log",
        description="Destination filename inside the session workspace.",
        examples=["failure.log"]
    )


class DownloadLogResponse(BaseModel):
    """Response contract for download_log tool."""
    status: str = Field(..., description="Download and staging outcome status", examples=["staged"])
    file_path: str = Field(..., description="Staged file path in workspace", examples=["failure.log"])
    size_bytes: int = Field(..., description="File size in bytes", examples=[524288])
    hint: Optional[str] = Field(default=None, description="Guidance on next recommended action", examples=["Call read_workspace_log to inspect or load lines into memory."])


class ReadLogInput(BaseModel):
    """Input contract for reading file content from the session workspace."""
    reasoning: str = Field(
        ...,
        description="Mandatory justification explaining why the file content is being read.",
        examples=["Reading raw failure.log from workspace into memory for telemetry filtering and compression."]
    )
    file_path: str = Field(
        default="failure.log",
        description="Relative file path in the session workspace to read.",
        examples=["failure.log"]
    )


class ReadLogResponse(BaseModel):
    """Response contract for read_workspace_log tool."""
    content: str = Field(..., description="Retrieved plaintext content of the file", examples=["[2026-02-26 06:00:10] [INFO] Reactor start sequence initiated..."])
    line_count: int = Field(..., description="Total number of lines in the content", examples=[14520])
    hint: Optional[str] = Field(default=None, description="Guidance on next recommended action", examples=["Process lines in memory to extract high-severity events between 06:00 and 22:00."])


class GrepWorkspaceInput(BaseModel):
    """Input contract for running targeted grep searches in the session workspace."""
    reasoning: str = Field(
        ...,
        description="Mandatory justification explaining the purpose of the grep pattern search.",
        examples=["Searching for all CRIT or ERRO events occurring on pump or tank components."]
    )
    pattern: str = Field(
        ...,
        description="Regular expression or keyword string to search for.",
        examples=["CRIT|ERRO|trip|WTANK|PUMP"]
    )
    file_path: str = Field(
        default="failure.log",
        description="Relative file path in workspace to search.",
        examples=["failure.log"]
    )
    flags: Optional[List[str]] = Field(
        default=None,
        description="Optional allowed grep flags, e.g. ['-i', '-n']",
        examples=[["-i", "-n"]]
    )


class GrepWorkspaceResponse(BaseModel):
    """Response contract for grep_workspace_log tool."""
    matches: str = Field(..., description="Matching log lines output by grep", examples=["[2026-02-26 06:04:15] [CRIT] ECCS8 runaway outlet temp..."])
    match_count: int = Field(..., description="Number of matching lines found", examples=[42])
    hint: Optional[str] = Field(default=None, description="Guidance on next recommended action", examples=["Parse matched lines to assemble the condensed failure narrative."])


class CountTokensInput(BaseModel):
    """Input contract for token counting verification."""
    reasoning: str = Field(
        ...,
        description="Mandatory justification for checking token count before submission.",
        examples=["Validating that condensed log candidate string strictly satisfies the 1,500 token ceiling."]
    )
    text: str = Field(
        ...,
        description="Candidate condensed log multiline text to validate.",
        examples=["[2026-02-26 06:04] [CRIT] ECCS8 runaway outlet temp...\n[2026-02-26 06:11] [WARN] PWR01 ripple..."]
    )


class CountTokensResponse(BaseModel):
    """Response contract for count_tokens tool."""
    token_count: int = Field(..., description="Calculated token count according to tokenizer/Vertex AI", examples=[1380])
    is_valid: bool = Field(..., description="True if token_count <= max_allowed (1,500)", examples=[True])
    max_allowed: int = Field(default=1500, description="Strict ceiling allowed by Centrala", examples=[1500])
    safe_target: int = Field(default=1400, description="Recommended safe threshold", examples=[1400])
    hint: Optional[str] = Field(default=None, description="Guidance on whether further compression is needed", examples=["Token budget is valid. Ready for verification."])


class VerifySolutionInput(BaseModel):
    """Input contract for submitting condensed logs to Centrala verification endpoint."""
    reasoning: str = Field(
        ...,
        description="Mandatory justification for submitting the candidate log to Centrala.",
        examples=["Submitting validated condensed log (1380 tokens) via cr-mcp-web-gateway to $AIDEVS_API_VERIFY."]
    )
    logs: str = Field(
        ...,
        description="Condensed multiline string where each line represents a single key event.",
        examples=["[2026-02-26 06:04] [CRIT] ECCS8 runaway outlet temp...\n[2026-02-26 06:11] [WARN] PWR01 input ripple..."]
    )


class VerifySolutionResponse(BaseModel):
    """Response contract for verify_solution tool."""
    code: int = Field(..., description="Response status code returned by Centrala (0 = success)", examples=[0])
    message: str = Field(..., description="Response message or feedback text from Centrala technicians", examples=["OK {FLG:...}"])
    flag: Optional[str] = Field(default=None, description="Extracted course completion flag if verification succeeded", examples=["{FLG:...}"])
    feedback: Optional[str] = Field(default=None, description="Diagnostic feedback on missing or unclear components", examples=["Missing telemetry for PUMP02."])
    is_success: bool = Field(..., description="True if the flag was successfully captured", examples=[True])
    hint: Optional[str] = Field(default=None, description="Guidance on next action (e.g. write run_notes.txt or remediate missing component)", examples=["Success! Save summary to run_notes.txt."])


# --- Parsed Telemetry Data Models ---

class TelemetryEvent(BaseModel):
    """Structured representation of a single log event."""
    timestamp_raw: str = Field(..., description="Original raw timestamp from log", examples=["2026-02-26 06:04:12"])
    date_str: str = Field(..., description="Date string in YYYY-MM-DD format", examples=["2026-02-26"])
    time_str: str = Field(..., description="Time string in HH:MM format", examples=["06:04"])
    severity: str = Field(..., description="Severity level bracketed or tag", examples=["[CRIT]"])
    component_id: str = Field(..., description="Identified component alphanumeric tag", examples=["ECCS8"])
    description: str = Field(..., description="Concise paraphrased description of the incident", examples=["runaway outlet temp. Protection interlock initiated reactor trip."])
    raw_line: str = Field(..., description="Exact raw line as it appeared in the log", examples=["[2026-02-26 06:04:12] [CRIT] ECCS8 runaway outlet temp. Protection interlock initiated reactor trip."])

    def to_condensed_line(self) -> str:
        """Formats into the required: [YYYY-MM-DD HH:MM] [SEVERITY] COMPONENT_ID Description."""
        desc = self.description.strip()
        comp = self.component_id.strip()
        if comp != "UNKNOWN" and comp not in desc:
            return f"[{self.date_str} {self.time_str}] {self.severity} {comp} {desc}".strip()
        return f"[{self.date_str} {self.time_str}] {self.severity} {desc}".strip()
