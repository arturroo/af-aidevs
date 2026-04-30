from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

# --- Base Models ---

class BaseResponse(BaseModel):
    """Base class for all tool outputs to ensure consistent error handling."""
    error: Optional[str] = Field(None, description="Technical error message if the operation failed. If None, the operation was successful.")
    hint: Optional[str] = Field(None, description="Optional advice or next steps for the agent based on the tool's result.")

# --- list_local_files ---

class ListFilesInput(BaseModel):
    reasoning: str = Field(..., description="Why do you need to list the files at this moment?")

class ListFilesOutput(BaseResponse):
    files: List[str] = Field(default_factory=list, description="List of relative file names found in the documentation sandbox.", example=["index.md", "trasy-wylaczone.png"])
    message: Optional[str] = Field(None, description="Optional status message or hint about the listing process.")

# --- read_local_text_file ---

class ReadFileInput(BaseModel):
    reasoning: str = Field(..., description="Why are you reading this specific file? What are you looking for?")
    filename: str = Field(..., description="Precise name of the file to read (must be relative to data/ folder).", example="index.md")

class ReadFileOutput(BaseResponse):
    content: Optional[str] = Field(None, description="The full text content of the requested file.")

# --- load_image_to_context ---

class LoadImageInput(BaseModel):
    reasoning: str = Field(..., description="Why do you need to analyze this image? What information do you expect to find?")
    filename: str = Field(..., description="Name of the image file to analyze (e.g., 'trasy-wylaczone.png').", example="trasy-wylaczone.png")

# --- http_get_from_hub ---

class HttpGetInput(BaseModel):
    reasoning: str = Field(..., description="Why are you fetching this file from the Hub? How does it help the mission?")
    filename: str = Field(..., description="Target filename or path on the Hub (e.g., 'index.html').", example="zalacznik-A.md")
    headers: Optional[Dict[str, str]] = Field(
        default=None, 
        description="Custom HTTP headers for authentication or special access levels (e.g., YELLOW level).",
        example={"x-secret-header": "value"}
    )

class HttpGetOutput(BaseResponse):
    status: int = Field(default=200, description="HTTP response status code.", ge=100, le=599, example=200)
    headers: Dict[str, str] = Field(default_factory=dict, description="Complete dictionary of response headers received from the Hub.")
    filename: Optional[str] = Field(None, description="The name of the file as saved in the local sandbox. Use this name with other file tools.", example="zalacznik-A.md")
    message: Optional[str] = Field(None, description="Human-readable status of the fetch operation.")

# --- submit_declaration ---

class SubmitDeclarationInput(BaseModel):
    reasoning: str = Field(..., description="Justification for submitting the declaration now. Did you verify all required fields?")
    declaration: Dict[str, Any] = Field(
        ..., 
        description="The final transport declaration object structured according to the lesson template (Appendix E)."
    )

class SubmitDeclarationOutput(BaseResponse):
    status: int = Field(default=200, description="Verification server HTTP status code.", ge=100, le=599, example=200)
    headers: Dict[str, str] = Field(default_factory=dict, description="Response headers from the verification server (may contain secrets!).")
    body: Optional[str] = Field(None, description="Raw response body from the verification server.")

# --- get_current_date ---

class GetDateInput(BaseModel):
    reasoning: str = Field(..., description="Why do you need to know the current date/time?")

class GetDateOutput(BaseResponse):
    current_date: str = Field(..., description="The current date and time in Europe/Zurich.")

# --- Agent Interaction ---

class AgentResponse(BaseModel):
    """The final structured response from the agent, including reasoning for audit purposes."""
    reasoning: str = Field(..., description="Detailed explanation of the agent's decision-making process and findings (internal monologue).")
    answer: str = Field(..., description="The final answer, summary, or response directed to the user.")
