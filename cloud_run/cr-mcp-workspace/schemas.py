from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# ==========================================
# 1. TOOL OUTPUTS (Method-Specific Responses)
# ==========================================

class ReadFileResponse(BaseModel):
    content: str = Field(
        description="The complete content of the file read from the session workspace",
        json_schema_extra={"example": "Hello, world! File contents here."}
    )
    hint: Optional[str] = Field(
        default=None,
        description="Optional warning or system notice regarding the read file operation",
        json_schema_extra={"example": "File is empty."}
    )

class WriteFileResponse(BaseModel):
    status: str = Field(
        description="Operation status: 'success' or 'error'",
        json_schema_extra={"example": "success"}
    )
    message: str = Field(
        description="Detail message confirming write outcome or error details",
        json_schema_extra={"example": "File successfully written to output.txt"}
    )
    hint: Optional[str] = Field(
        default=None,
        description="Optional progressive disclosure or next-step guidance for the agent",
        json_schema_extra={"example": "You can now read this file to verify its contents."}
    )

class ListFilesResponse(BaseModel):
    status: str = Field(
        description="Operation status: 'success' or 'error'",
        json_schema_extra={"example": "success"}
    )
    files: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="List of file and directory metadata matching the listed directory",
        json_schema_extra={"example": [{"name": "notes.md", "type": "file", "size_bytes": 1024}]}
    )
    message: Optional[str] = Field(
        default=None,
        description="Informative message about directory state or errors",
        json_schema_extra={"example": "Directory is empty"}
    )
    hint: Optional[str] = Field(
        default=None,
        description="Progressive disclosure hint indicating what the agent can do next",
        json_schema_extra={"example": "Use '.' to list the root workspace directory."}
    )

class GrepResponse(BaseModel):
    results: str = Field(
        description="The raw string matching the pattern within the searched file, including line numbers if requested",
        json_schema_extra={"example": "12: import os\n45: logger.info('System start')"}
    )
    hint: Optional[str] = Field(
        default=None,
        description="Optional system note about grep limitations or outcome",
        json_schema_extra={"example": "No matches found (File is empty)."}
    )

class HeadResponse(BaseModel):
    content: str = Field(
        description="The top N lines read from the file",
        json_schema_extra={"example": "line 1\nline 2\nline 3"}
    )
    hint: Optional[str] = Field(
        default=None,
        description="Warning indicating if lines were truncated due to length/byte limits",
        json_schema_extra={"example": "Some lines were truncated because they exceeded the 8KB limit."}
    )

class TailResponse(BaseModel):
    content: str = Field(
        description="The bottom N lines read from the file",
        json_schema_extra={"example": "line 98\nline 99\nline 100"}
    )
    hint: Optional[str] = Field(
        default=None,
        description="Warning indicating if file tail search exceeded size boundaries and triggered truncation",
        json_schema_extra={"example": "File size exceeds limits. Showing last 64KB."}
    )

class ReadMarkdownSectionResponse(BaseModel):
    content: str = Field(
        description="Parsed content belonging strictly to the requested markdown section",
        json_schema_extra={"example": "### Architecture\nWe use microservices deployed on Cloud Run."}
    )
    hint: Optional[str] = Field(
        default=None,
        description="Warning indicating if the heading was missing or if the file was empty",
        json_schema_extra={"example": "Header 'Setup' not found in the document."}
    )

class ListMarkdownSectionsResponse(BaseModel):
    sections: List[Dict[str, Any]] = Field(
        description="List of parsed headings containing their level and title",
        json_schema_extra={"example": [{"level": 1, "title": "Overview"}, {"level": 2, "title": "Setup"}]}
    )
    hint: Optional[str] = Field(
        default=None,
        description="Optional warnings or notifications",
        json_schema_extra={"example": "Markdown file parsed successfully."}
    )

# ==========================================
# 2. TOOL INPUTS (Args Schemas for Reference)
# ==========================================

class ReadFileInput(BaseModel):
    reasoning: str = Field(
        description="Mandatory justification explaining why this file needs to be read",
        json_schema_extra={"example": "Reading notes.md to find API endpoint keys"}
    )
    file_path: str = Field(
        description="Relative path to the file to read from the session workspace",
        json_schema_extra={"example": "notes.md"}
    )

class WriteFileInput(BaseModel):
    reasoning: str = Field(
        description="Mandatory justification explaining why this file is being written",
        json_schema_extra={"example": "Saving verification results to output.txt"}
    )
    file_path: str = Field(
        description="Relative path to the file to write in the session workspace",
        json_schema_extra={"example": "output.txt"}
    )
    content: str = Field(
        description="Content to write into the file",
        json_schema_extra={"example": "Task complete: success"}
    )

class ListFilesInput(BaseModel):
    reasoning: str = Field(
        description="Mandatory justification explaining why directory listing is needed",
        json_schema_extra={"example": "Listing workspace root to find available task files"}
    )
    path: str = Field(
        default=".",
        description="Directory path relative to your session workspace to list.",
        json_schema_extra={"example": "."}
    )

class GrepInput(BaseModel):
    reasoning: str = Field(
        description="Mandatory justification explaining why this search is needed",
        json_schema_extra={"example": "Searching for BQ_AUDIT_TABLE env var in code"}
    )
    pattern: str = Field(
        description="The pattern or string to search for",
        json_schema_extra={"example": "verify_url"}
    )
    file_path: str = Field(
        description="The relative path of the file to search in",
        json_schema_extra={"example": "main.py"}
    )
    flags: Optional[List[str]] = Field(
        default=None,
        description="Optional grep flags: -i, -n, -v, -C, -A, -B",
        json_schema_extra={"example": ["-i", "-n"]}
    )

class HeadInput(BaseModel):
    reasoning: str = Field(
        description="Mandatory justification explaining why this head read is needed",
        json_schema_extra={"example": "Inspecting first 10 lines of CSV to check column structure"}
    )
    file_path: str = Field(
        description="Relative path to the file in the workspace",
        json_schema_extra={"example": "categorize.csv"}
    )
    lines: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of lines to read from the top (max 100)",
        json_schema_extra={"example": 10}
    )

class TailInput(BaseModel):
    reasoning: str = Field(
        description="Mandatory justification explaining why this tail read is needed",
        json_schema_extra={"example": "Inspecting last 5 lines of log to check for final success flags"}
    )
    file_path: str = Field(
        description="Relative path to the file in the workspace",
        json_schema_extra={"example": "run.log"}
    )
    lines: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of lines to read from the bottom (max 100)",
        json_schema_extra={"example": 10}
    )

class ReadMarkdownSectionInput(BaseModel):
    reasoning: str = Field(
        description="Mandatory justification explaining why this markdown section is being read",
        json_schema_extra={"example": "Reading 'Verification' section from PRD"}
    )
    file_path: str = Field(
        description="Relative path to the markdown file in the workspace",
        json_schema_extra={"example": "PRD.md"}
    )
    header_title: str = Field(
        description="The heading title to search for (case-insensitive)",
        json_schema_extra={"example": "Verification"}
    )

class ListMarkdownSectionsInput(BaseModel):
    reasoning: str = Field(
        description="Mandatory justification explaining why listing headings is needed",
        json_schema_extra={"example": "Listing headers to locate the Verification steps section"}
    )
    file_path: str = Field(
        description="Relative path to the markdown file in the workspace",
        json_schema_extra={"example": "PRD.md"}
    )

