from typing import Literal
from pydantic import BaseModel, Field

class ArmorRequest(BaseModel):
    input: str = Field(description="The text to analyze for safety")
    policy_context: str = Field(description="Context defining what is considered safe or unsafe for this specific invocation")

class ArmorResponse(BaseModel):
    decision: Literal["safe", "unsafe"] = Field(
        description="The safety evaluation result. Must be either 'safe' or 'unsafe'.",
        json_schema_extra={"example": "safe"}
    )
    reasoning: str = Field(
        description="Detailed explanation of the decision based on the provided policy context.",
        json_schema_extra={"example": "The input does not contain any sensitive information or policy violations."}
    )
