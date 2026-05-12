import os
from google import genai
from google.genai import types
from schemas import ArmorResponse, ArmorRequest
from af_aidevs.utils.prompts import load_system_prompt

def check_safety(request: ArmorRequest) -> ArmorResponse:
    """
    Evaluates input text against a provided policy context using Gemini Flash-Lite.
    Reads system instruction and model configuration from system_prompt.md.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    prompt_config = load_system_prompt(base_dir=current_dir, filename="system_prompt.md")
    
    system_instruction_template = prompt_config.system_prompt
    model = prompt_config.model
    temperature = prompt_config.temperature
    location = prompt_config.model_region
    
    # Format system instruction with the policy context
    system_instruction = system_instruction_template.format(policy_context=request.policy_context)
    
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
    
    client = genai.Client(
        vertexai=True,
        project=project_id,
        location=location
    )
    
    response = client.models.generate_content(
        model=model,
        contents=request.input,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=ArmorResponse,
        )
    )
    
    return response.parsed
