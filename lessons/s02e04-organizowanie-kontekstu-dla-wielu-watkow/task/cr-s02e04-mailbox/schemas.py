from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = Field(default="ok", examples=["ok"])
    service: str = Field(default="cr-s02e04-mailbox", examples=["cr-s02e04-mailbox"])
    version: str = Field(default="0.1.0", examples=["0.1.0"])


class ZmailCallRequest(BaseModel):
    """Input contract for querying the compromised operator Zmail API."""
    action: str = Field(
        description="Zmail API action (e.g. 'help', 'getInbox', 'search', 'getMessage')",
        examples=["help"],
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional dictionary of parameters for the action (e.g. {'query': 'from:proton.me', 'page': 1})",
        examples=[{"query": "from:proton.me"}],
    )
    reasoning: str = Field(
        description="Mandatory justification for invoking this action",
        examples=["Querying mailbox for emails from defector Wiktor (proton.me) to find power plant attack date."],
    )


class ZmailCallResponse(BaseModel):
    """Response contract returned by the Zmail API wrapper."""
    action: str = Field(description="The action that was executed", examples=["help"])
    result: Dict[str, Any] = Field(description="Raw dictionary result returned by the API", examples=[{"actions": ["getInbox", "search"]}])
    hint: Optional[str] = Field(
        default=None,
        description="Progressive instruction on next investigation steps",
        examples=["Examine returned messages and use get_email_details to inspect message bodies."],
    )


class GetEmailDetailsRequest(BaseModel):
    """Input contract for fetching the complete body of a specific email message."""
    message_id: str = Field(
        description="Unique identifier of the email message to fetch",
        examples=["msg_84920"],
    )
    reasoning: str = Field(
        description="Why this specific message needs full body inspection",
        examples=["Inspecting body of security department alert to extract SEC- confirmation code."],
    )


class GetEmailDetailsResponse(BaseModel):
    """Response contract containing full email body sanitized by Model Armor."""
    message_id: str = Field(description="The message identifier", examples=["msg_84920"])
    subject: str = Field(default="", description="Email subject line", examples=["Security Alert - Confirmation"])
    sender: str = Field(default="", description="Sender address", examples=["security@system.local"])
    body: str = Field(description="Full text body of the email message", examples=["Your ticket confirmation is SEC-..."])
    is_sanitized: bool = Field(
        description="Indicates whether content was screened and passed by cr-model-armor",
        examples=[True],
    )
    hint: Optional[str] = Field(
        default=None,
        description="Guidance on relevant entities identified in the body",
        examples=["Look for 32-character ticket codes starting with SEC- and dates in YYYY-MM-DD format."],
    )


class VerifyTaskRequest(BaseModel):
    """Contract for submitting final extracted values to Centrala verification endpoint."""
    date: str = Field(
        description="Scheduled attack date on power plant strictly in YYYY-MM-DD format",
        examples=["2026-02-28"],
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    password: str = Field(
        description="Employee system password found within mailbox correspondence",
        examples=["secretPass123"],
        min_length=1,
    )
    confirmation_code: str = Field(
        description="Security ticket confirmation code starting with SEC- (alphanumeric, e.g. SEC-...)",
        examples=["SEC-c1e598764329cc9c377ef1d029be8ceb"],
        pattern=r"^SEC-[A-Za-z0-9]{20,40}$",
    )
    reasoning: str = Field(
        description="Justification verifying all three values are collected and validated",
        examples=["Extracted attack date from Wiktor's email, password from welcome mail, and code from security ticket."],
    )


class VerifyTaskResponse(BaseModel):
    """Response contract from Centrala verification hub."""
    status: str = Field(description="Status of verification attempt ('success' or 'rejected')", examples=["success"])
    flag: Optional[str] = Field(default=None, description="Course completion flag if accepted", examples=["{FLG:...}"])
    feedback: Optional[str] = Field(default=None, description="Feedback or rejection error message from Centrala", examples=[None])
    hint: Optional[str] = Field(default=None, description="Next steps advice based on hub response", examples=["Task complete."])


class RunTaskRequest(BaseModel):
    """Request payload for Cloud Run POST /run endpoint."""
    backend: str = Field(default="langchain", description="Agent execution backend ('langchain' or 'adk')", examples=["langchain"])
    max_iterations: int = Field(default=10, description="Maximum polling iterations across the active mailbox", ge=1, le=50)


class RunTaskResponse(BaseModel):
    """Envelope response returned by the investigation service."""
    status: str = Field(description="Execution outcome ('success', 'partial', 'failed')", examples=["success"])
    session_id: str = Field(description="Unique standardized session trace identifier", examples=["s02e04_langchain_20260908_153000"])
    flag: Optional[str] = Field(default=None, description="Captured course flag", examples=["{FLG:...}"])
    date: Optional[str] = Field(default=None, description="Extracted attack date in YYYY-MM-DD format", examples=["2026-02-28"])
    password: Optional[str] = Field(default=None, description="Extracted employee system password", examples=["secretPass123"])
    confirmation_code: Optional[str] = Field(default=None, description="Extracted security confirmation code", examples=["SEC-A1B2C3D4E5F6G7H8I9J0K1L2M3N4"])
    iterations: int = Field(description="Total polling iterations performed", examples=[2])
    backend: str = Field(description="Backend framework used", examples=["langchain"])
    notes_file: Optional[str] = Field(default="run_notes.txt", description="Workspace path where execution report was written")
