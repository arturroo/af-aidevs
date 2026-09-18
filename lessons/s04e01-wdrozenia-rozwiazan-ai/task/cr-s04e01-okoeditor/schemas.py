from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    status: str = Field(
        default="healthy",
        description="Health status of the microservice",
        examples=["healthy"],
    )
    service: str = Field(
        default="cr-s04e01-okoeditor",
        description="Name of the Cloud Run microservice",
        examples=["cr-s04e01-okoeditor"],
    )
    timestamp: str = Field(
        description="Current server timestamp in ISO format",
        examples=["2026-09-18T22:00:00+02:00"],
    )


class RunTaskRequest(BaseModel):
    backend: Literal["langchain", "adk"] = Field(
        default="langchain",
        description="Agent backend selection: 'langchain' or 'adk'",
        examples=["langchain", "adk"],
    )
    session_id: str | None = Field(
        default=None,
        description="Optional custom session identifier for audit and tracing tracking",
        examples=["session_oko_20260918_220000"],
    )
    max_iterations: int | None = Field(
        default=30,
        description="Optional maximum round / recursion limit for agent execution",
        examples=[30],
    )


class RunTaskResponse(BaseModel):
    status: str = Field(
        description="Execution status of the task ('success' or 'error')",
        examples=["success", "error"],
    )
    backend: str = Field(
        description="The agent backend used for execution",
        examples=["langchain", "adk"],
    )
    session_id: str = Field(
        description="The unique session ID associated with this execution run",
        examples=["s04e01_langchain_20260918_220000"],
    )
    flag: str = Field(
        description="Extracted course verification flag, or '[REDACTED_FLAG]' in audit reports",
        examples=["{FLG:...}", "[REDACTED_FLAG]"],
    )
    actions_taken: list[str] = Field(
        default_factory=list,
        description="List of covert backdoor actions executed during the run",
        examples=[
            [
                "help",
                "get_reports",
                "update_report",
                "get_tasks",
                "update_task",
                "add_incident",
                "done",
            ]
        ],
    )
    reasoning: str = Field(
        description="Auditable chain-of-thought and verification summary of the agent's operations",
        examples=[
            "Discovered backdoor API via help, reclassified Skolwin incident to animal activity, resolved Skolwin task, injected Komarowo diversion, and confirmed completion with done."
        ],
    )

    @field_validator("reasoning", mode="before")
    @classmethod
    def coerce_reasoning_to_str(cls, v: Any) -> str:
        if isinstance(v, list):
            return "\n".join(
                item.get("text", str(item)) if isinstance(item, dict) else str(item)
                for item in v
            )
        return str(v)


class CallOkoApiInput(BaseModel):
    action: str = Field(
        description="The backdoor API action name to invoke (e.g. 'help', 'done', or specific introspection/mutation commands discovered via help)",
        examples=["help", "done"],
    )
    params: dict[str, Any] | None = Field(
        default=None,
        description="Optional payload dictionary parameters required by the specific action",
        examples=[{"id": "123", "category": "animals"}],
    )
    reasoning: str = Field(
        description="Mandatory justification explaining why this action and these parameters are being executed",
        examples=[
            "Querying help to inspect all available backdoor commands and payload schemas"
        ],
    )


class CallOkoApiResponse(BaseModel):
    status: str = Field(
        description="Execution status ('success' or 'error')",
        examples=["success", "error"],
    )
    action: str = Field(
        description="The backdoor action that was executed",
        examples=["help", "done"],
    )
    code: int = Field(
        description="Response code returned by Centrala API (0 indicates success)",
        examples=[0, -9999],
    )
    message: str = Field(
        description="Response message, error details, or command output from Centrala",
        examples=["Report updated successfully", "{FLG:...}"],
    )
    data: Any | None = Field(
        default=None,
        description="Optional structured response payload or schema definitions returned by Centrala",
        examples=[{"available_actions": ["help", "done"]}],
    )
    hint: str | None = Field(
        default=None,
        description="Guidance for the agent on progressive disclosure or the next logical step",
        examples=[
            "Analyze the available actions from help to determine how to query and update reports and tasks."
        ],
    )


class AgentResponse(BaseModel):
    reasoning: str = Field(
        description="Comprehensive audit reasoning detailing all actions executed to complete the mission",
        examples=[
            "Successfully introspected API via help, updated Skolwin report to wildlife, closed task with beaver sightings, created Komarowo diversion, and captured course flag via done."
        ],
    )
    flag: str = Field(
        description="The retrieved course verification flag {FLG:...}",
        examples=["{FLG:...}"],
    )
    actions_taken: list[str] = Field(
        default_factory=list,
        description="Chronological record of API actions invoked during execution",
        examples=[["help", "update_report", "update_task", "create_incident", "done"]],
    )
    summary: str = Field(
        description="Concise human-readable mission summary",
        examples=[
            "OKO surveillance records successfully manipulated. Tracks covered for Skolwin and diversion deployed to Komarowo."
        ],
    )


class FetchOkoPageInput(BaseModel):
    page: str = Field(
        default="incydenty",
        description="The subpage of OKO surveillance panel to fetch (e.g. 'incydenty', 'zadania', 'notatki', or specific path)",
        examples=["incydenty", "zadania", "notatki"],
    )
    reasoning: str = Field(
        description="Mandatory justification explaining why this subpage is being inspected",
        examples=[
            "Fetching active incidents to find Skolwin incident ID and report details"
        ],
    )


class FetchOkoPageResponse(BaseModel):
    status: str = Field(
        description="Status of page fetch operation ('success' or 'error')",
        examples=["success", "error"],
    )
    page: str = Field(
        description="The subpage that was fetched",
        examples=["incydenty", "zadania"],
    )
    html_file: str = Field(
        description="Relative path to saved raw HTML file in workspace",
        examples=["oko_incydenty.html"],
    )
    markdown_file: str = Field(
        description="Relative path to saved converted Markdown file in workspace",
        examples=["oko_incydenty.md"],
    )
    discovered_links: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of surveillance records with their 32-character hex IDs discovered on the page",
        examples=[
            [
                {
                    "page": "incydenty",
                    "id": "380792b2c86d9c5be670b3bde48e187b",
                    "title": "MOVE03 Trudne do klasyfikacji ruchy nieopodal miasta Skolwin",
                    "url": "/incydenty/380792b2c86d9c5be670b3bde48e187b",
                }
            ]
        ],
    )
    preview: str = Field(
        description="Concise textual or Markdown preview of the fetched page content",
        examples=["# Ostatnie incydenty\n\nMOVE03 Trudne do klasyfikacji ruchy..."],
    )
    hint: str | None = Field(
        default=None,
        description="Guidance on next steps with the discovered record IDs",
        examples=[
            "Use the discovered record ID with call_oko_api(action='update', ...) or inspect details with read_workspace_file."
        ],
    )


class ListWorkspaceFilesInput(BaseModel):
    path: str = Field(
        default=".",
        description="Directory path relative to the session workspace to list. Default is '.' for root.",
        examples=[".", "api_calls"],
    )
    reasoning: str = Field(
        default="",
        description="Mandatory justification explaining why listing files is needed",
        examples=[
            "Listing workspace root to discover saved surveillance reports and artifacts"
        ],
    )


class ListWorkspaceFilesResponse(BaseModel):
    status: str = Field(
        description="Status of file listing operation ('success' or 'error')",
        examples=["success", "error"],
    )
    files: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of files and directories in the requested path with metadata",
        examples=[[{"name": "oko_incydenty.md", "type": "file", "size_bytes": 1024}]],
    )
    hint: str | None = Field(
        default=None,
        description="Hint for using the listed files",
        examples=["Use read_workspace_file to read the contents of a specific file."],
    )
