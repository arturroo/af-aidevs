import os
import httpx
from typing import Optional, Dict
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
AIDEVS_DANE_DOC = os.getenv("AIDEVS_DANE_DOC")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

from schemas import HttpGetInput, HttpGetOutput

@tool("http_get_from_hub", args_schema=HttpGetInput)
async def http_get_from_hub(filename: str, reasoning: str, headers: Optional[Dict[str, str]] = None) -> HttpGetOutput:
    """Performs an HTTP GET request to the SPK Hub."""
    url = f"{AIDEVS_DANE_DOC}/{filename}"
    
    # Prepare headers
    actual_headers = headers.copy() if headers else {}
    actual_headers.setdefault("User-Agent", "Mozilla/5.0 SPK-Agent/3.1")
    
    async with httpx.AsyncClient(timeout=10.0, http2=False) as client:
        try:
            response = await client.get(url, headers=actual_headers)
            
            # Security check for the filename when saving
            safe_path = (DATA_DIR / filename).resolve()
            if not str(safe_path).startswith(str(DATA_DIR)):
                return HttpGetOutput(status=403, headers={}, error="Security Error: Attempted directory traversal.")

            # Save body to file
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            if "image" in response.headers.get("Content-Type", ""):
                safe_path.write_bytes(response.content)
            else:
                safe_path.write_text(response.text, encoding="utf-8")

            # Returning structured Pydantic model
            hint = "If this is an image (PNG/JPG), use 'load_image_to_context' to analyze it." if "image" in response.headers.get("Content-Type", "") else None
            return HttpGetOutput(
                status=response.status_code,
                headers=dict(response.headers),
                filename=filename,
                message=f"File {filename} successfully fetched and saved locally.",
                hint=hint
            )
        except Exception as e:
            return HttpGetOutput(status=500, headers={}, error=str(e))
