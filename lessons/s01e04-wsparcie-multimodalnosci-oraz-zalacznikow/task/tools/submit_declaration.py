import os
import httpx
from typing import Dict, Any
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from dotenv import load_dotenv
load_dotenv()
AIDEVS_VERIFY = os.getenv("AIDEVS_VERIFY")
AIDEVS_API_KEY = os.getenv("AIDEVS_API_KEY")

from schemas import SubmitDeclarationInput, SubmitDeclarationOutput

@tool("submit_declaration", args_schema=SubmitDeclarationInput)
async def submit_declaration(declaration: Dict[str, Any], reasoning: str) -> SubmitDeclarationOutput:
    """Submits the final declaration to the verification server."""
    if not AIDEVS_VERIFY:
        return SubmitDeclarationOutput(status=500, headers={}, body="", error="AIDEVS_VERIFY env var not set.")
    
    try:
        payload = {
            "apikey": AIDEVS_API_KEY,
            "task": "sendit",
            "answer": {
                "declaration": declaration
            }
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(AIDEVS_VERIFY, json=payload)
            hint = "If you got errors, check the 'body' for clues on which declaration fields are incorrect." if response.status_code != 200 else "Mission accomplished! You can now provide the final response."
            return SubmitDeclarationOutput(
                status=response.status_code,
                headers=dict(response.headers),
                body=response.text,
                hint=hint
            )
    except httpx.RequestError as e:
        # Network-level error (no response from server)
        return SubmitDeclarationOutput(status=0, headers={}, body="", error=f"Network Error: {str(e)}")
    except Exception as e:
        # Unexpected logic error
        return SubmitDeclarationOutput(status=500, headers={}, body="", error=f"Internal Error: {str(e)}")
