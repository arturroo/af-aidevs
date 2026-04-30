from langchain_core.tools import tool
from pathlib import Path

# Important: This tool uses BASE_DIR from the environment/calling context
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

from schemas import ListFilesInput, ListFilesOutput

@tool("list_local_files", args_schema=ListFilesInput)
def list_local_files(reasoning: str) -> ListFilesOutput:
    """Lists all files available in your local sandbox."""
    if not DATA_DIR.exists():
        return ListFilesOutput(files=[], message="No files found. Sandbox is empty.", hint="Check if you need to fetch files from the Hub first.")
    
    # Premium recursive listing using rglob
    files = [str(f.relative_to(DATA_DIR)) for f in DATA_DIR.rglob("*") if f.is_file()]
    return ListFilesOutput(
        files=files, 
        hint="Now use 'read_local_text_file' to inspect the content of the found files, especially those that look like notes or metadata."
    )
