import logging
from langchain_core.tools import tool
from pathlib import Path
from schemas import ListFilesInput, ListFilesOutput

logger = logging.getLogger("tools.list_local_files")

# Important: This tool uses BASE_DIR from the environment/calling context
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
logger.info(f"==== TOOL DEBUG ==== list_local_files: DATA_DIR is {DATA_DIR}")


@tool("list_local_files", args_schema=ListFilesInput)
def list_local_files(reasoning: str) -> ListFilesOutput:
    """Lists all files available in your local sandbox."""
    logger.info(f"==== TOOL DEBUG ==== list_local_files: DATA_DIR is {DATA_DIR}")
    
    if not DATA_DIR.exists():
        logger.error(f"==== TOOL DEBUG ==== list_local_files: DATA_DIR DOES NOT EXIST!")
        result = ListFilesOutput(files=[], message="No files found. Sandbox is empty.", hint="Check if you need to fetch files from the Hub first.")
        logger.info(f"==== TOOL DEBUG ==== list_local_files: Returning {result}")
        return result
    
    # Premium recursive listing using rglob
    files = [str(f.relative_to(DATA_DIR)) for f in DATA_DIR.rglob("*") if f.is_file()]
    result = ListFilesOutput(
        files=files, 
        hint="Now use 'read_local_text_file' to inspect the content of the found files, especially those that look like notes or metadata."
    )
    logger.info(f"==== TOOL DEBUG ==== list_local_files: Found {len(files)} files. Returning {result}")
    return result
