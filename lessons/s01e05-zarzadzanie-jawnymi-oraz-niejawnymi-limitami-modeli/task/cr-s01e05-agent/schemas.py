from pydantic import BaseModel, Field
from typing import Any, Dict

class AgentResponse(BaseModel):
    """Schema for the final response of the agent."""
    reasoning: str = Field(
        ...,
        description="Detailed step-by-step reasoning explaining how you arrived at the final answer.",
        example="I first called the API with the 'help' action, then I extracted the required parameters..."
    )
    answer: str = Field(
        ...,
        description="The final answer or flag obtained from the task.",
        example="{FLG:REDACTED}"
    )

class APICallInput(BaseModel):
    """Schema for calling the central API endpoint."""
    reasoning: str = Field(
        ...,
        description="Reasoning for why you are making this specific API call and what you expect to achieve.",
        example="I need to know available actions, so I am calling the API with the 'help' action."
    )
    answer: Dict[str, Any] = Field(
        ...,
        description="The payload to send in the 'answer' field of the API request body. Always provide a valid JSON object.",
        example={"action": "help"}
    )
