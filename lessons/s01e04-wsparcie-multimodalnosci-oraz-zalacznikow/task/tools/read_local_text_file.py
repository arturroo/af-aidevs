from langchain_core.tools import tool
from pathlib import Path

# Important: This tool uses DATA_DIR relative to the task folder
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

from schemas import ReadFileInput, ReadFileOutput

@tool("read_local_text_file", args_schema=ReadFileInput)
def read_local_text_file(filename: str, reasoning: str) -> ReadFileOutput:
    """Reads the content of a text or markdown file from your local sandbox.
    Use this to inspect documentation or metadata (headers.json files).
    """
    # Security: check for path traversal
    safe_path = (DATA_DIR / filename).resolve()
    if not str(safe_path).startswith(str(DATA_DIR)):
        return ReadFileOutput(error="Security Error: Attempted directory traversal detected.")
    
    if not safe_path.exists():
        return ReadFileOutput(error=f"File {filename} not found in the sandbox.", hint="Use 'list_local_files' to see the correct relative paths.")
    
    try:
        content = safe_path.read_text(encoding="utf-8")
        return ReadFileOutput(
            content=content,
            hint="Look for names, hardware types, or route codes. If this is a 'headers.json', use the found headers with 'http_get_from_hub' to fetch protected files."
        )
    except Exception as e:
        return ReadFileOutput(error=f"Error reading {filename}: {str(e)}")
