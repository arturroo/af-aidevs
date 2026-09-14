from typing import Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Canonical health check response."""
    status: str = Field(default="ok", description="Service readiness status.", examples=["ok"])
    service: str = Field(default="cr-s03e02-firmware", description="Microservice identifier.", examples=["cr-s03e02-firmware"])
    version: str = Field(default="0.1.0", description="Microservice version.", examples=["0.1.0"])


class RunTaskRequest(BaseModel):
    """Execution request payload for Cloud Run microservice endpoint."""
    backend: str = Field(
        default="langchain",
        description="Agent backend to execute: 'langchain' or 'adk'.",
        examples=["langchain", "adk"],
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session identifier. If omitted, a standardized ID will be generated.",
        examples=["s03e02_langchain_20260913_233000"],
    )


class RunTaskResponse(BaseModel):
    """Canonical task execution response containing outcome telemetry and flag."""
    status: str = Field(
        ...,
        description="Execution status: 'success' or 'failed'.",
        examples=["success", "failed"],
    )
    session_id: str = Field(
        ...,
        description="Standardized session identifier.",
        examples=["s03e02_langchain_20260913_233000"],
    )
    backend: str = Field(
        ...,
        description="Agent backend executed.",
        examples=["langchain", "adk"],
    )
    confirmation_code: Optional[str] = Field(
        default=None,
        description="Extracted ECCS runtime confirmation token.",
        examples=["ECCS-0123456789abcdef0123456789abcdef01234567"],
    )
    flag: Optional[str] = Field(
        default=None,
        description="Retrieved course completion flag.",
        examples=["{FLG:...}"],
    )
    steps_executed: int = Field(
        default=0,
        description="Total diagnostic iterations executed.",
        examples=[5],
    )
    details: Optional[str] = Field(
        default=None,
        description="Summary of firmware diagnostics outcome.",
        examples=["Cooler binary successfully patched and verified."],
    )


class ExecuteCommandInput(BaseModel):
    """Contract schema for executing non-interactive shell commands on the remote VM."""
    command: str = Field(
        ...,
        description="Shell command line to execute on the remote VM.",
        examples=["help", "ls -la /opt/firmware/cooler", "cat /opt/firmware/cooler/settings.ini"],
    )
    reasoning: str = Field(
        ...,
        description="Technical justification explaining why this shell command is executed.",
        examples=["List directory contents to discover available files and configuration templates."],
    )


class ExecuteCommandResponse(BaseModel):
    """Standardized response from remote VM shell execution."""
    output: str = Field(
        ...,
        description="Standard output and combined output text from the remote shell.",
        examples=["Available commands: help, ls, cat, echo, cp, rm"],
    )
    error: Optional[str] = Field(
        default=None,
        description="Error description if command execution encountered errors or was blocked.",
        examples=[None, "Command failed with exit code 1"],
    )
    code: int = Field(
        default=0,
        description="Numeric exit code returned by the shell API.",
        examples=[0, 1],
    )
    hint: Optional[str] = Field(
        default=None,
        description="Progressive guidance or actionable recommendations for next agent steps.",
        examples=["Inspect help command output to find available custom text editors."],
    )


class RebootVMInput(BaseModel):
    """Contract schema for requesting an emergency VM state reboot."""
    reasoning: str = Field(
        ...,
        description="Technical explanation why resetting the VM state is necessary.",
        examples=["Configuration files corrupted; reset needed to recover original state."],
    )


class RebootVMResponse(BaseModel):
    """Response returned after invoking emergency VM reboot."""
    status: str = Field(
        ...,
        description="Outcome of reboot request.",
        examples=["success", "error"],
    )
    message: str = Field(
        ...,
        description="Status description from remote environment.",
        examples=["VM reset to initial snapshot."],
    )
    hint: Optional[str] = Field(
        default=None,
        description="Guidance on subsequent steps.",
        examples=["Re-run command discovery to begin clean configuration."],
    )


class VerifySolutionInput(BaseModel):
    """Contract schema for submitting extracted ECCS token to verification hub."""
    confirmation_code: str = Field(
        ...,
        description="Extracted runtime confirmation token matching format ECCS-[a-zA-Z0-9]{40}.",
        examples=["ECCS-a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"],
    )
    reasoning: str = Field(
        ...,
        description="Technical justification for submitting this confirmation token.",
        examples=["Firmware binary returned runtime confirmation token upon successful startup."],
    )


class VerifySolutionResponse(BaseModel):
    """Response from Centrala verification hub."""
    status: str = Field(
        ...,
        description="Verification outcome: 'success' or 'failed'.",
        examples=["success", "failed"],
    )
    code: int = Field(
        ...,
        description="Verification API return code.",
        examples=[0, -1],
    )
    flag: Optional[str] = Field(
        default=None,
        description="Captured course verification flag if accepted.",
        examples=["{FLG:...}"],
    )
    message: str = Field(
        ...,
        description="Message from verification server.",
        examples=["OK"],
    )
    hint: Optional[str] = Field(
        default=None,
        description="Guidance on error resolution if rejected.",
        examples=["Verify token format and ensure cooler executed successfully."],
    )
