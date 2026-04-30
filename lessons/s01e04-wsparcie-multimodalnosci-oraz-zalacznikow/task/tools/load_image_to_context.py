import base64
from langchain_core.tools import tool
from pathlib import Path

# Important: This tool uses DATA_DIR relative to the task folder
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

from schemas import LoadImageInput

@tool("load_image_to_context", args_schema=LoadImageInput)
async def load_image_to_context(filename: str, reasoning: str) -> list:
    """Loads an image file from your local sandbox and provides it to the model.
    Use this when you need to see the content of a PNG/JPG file.
    """
    # Security: check for path traversal
    safe_path = (DATA_DIR / filename).resolve()
    if not str(safe_path).startswith(str(DATA_DIR)):
        return [{"error": "Security Error: Attempted directory traversal detected."}]

    if not safe_path.exists():
        return [{"error": f"Image {filename} not found."}]
    
    try:
        img_bytes = safe_path.read_bytes()
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")
        
        # Return multimodal content directly. 
        # Gemini 3.1 Flash supports this format in tool outputs.
        return [
            {"type": "text", "text": f"Here is the content of {filename}:"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
        ]
    except Exception as e:
        return [{"error": f"Error loading image: {str(e)}"}]
