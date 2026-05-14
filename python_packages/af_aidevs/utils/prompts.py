import os
import logging
import frontmatter
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

logger = logging.getLogger("utils.prompts")
DEFAULT_MODEL = "gemini-3-flash-preview"
DEFAULT_REGION = "global"
DEFAULT_TEMPERATURE = 0.0

class SystemPromptConfig(BaseModel):
    """Schema for system prompt and its associated metadata."""
    model_config = {'protected_namespaces': ()}
    
    system_prompt: str = Field(..., description="The actual system instruction text.")
    model: str = Field(DEFAULT_MODEL, description="The LLM model ID to use.")
    temperature: float = Field(DEFAULT_TEMPERATURE, description="The sampling temperature.")
    location: str = Field(DEFAULT_REGION, description="The GCP region for the model (e.g., europe-west6).")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional frontmatter metadata.")

def load_system_prompt(base_dir: str, filename: str = "system_prompt.md") -> SystemPromptConfig:
    """
    Loads the system instruction (prompt) and metadata from an external markdown file.
    
    Args:
        base_dir: The directory where the .md file is located.
        filename: The name of the file (default: system_prompt.md).
        
    Returns:
        A SystemPromptConfig object containing the prompt and validated metadata.
    """
    prompt_path = Path(base_dir) / filename
    
    # Fallback configuration
    fallback = SystemPromptConfig(
        system_prompt="You are a helpful assistant."
    )
    
    if not prompt_path.exists():
        logger.warning(f"{filename} not found in {base_dir}, using fallback.")
        return fallback
    
    try:
        prompt_config = frontmatter.load(prompt_path)
        metadata = prompt_config.metadata
        
        return SystemPromptConfig(
            system_prompt=prompt_config.content.strip(),
            model=metadata.get("model") or DEFAULT_MODEL,
            temperature=float(metadata.get("temperature")) or DEFAULT_TEMPERATURE,
            location=metadata.get("location") or metadata.get("model_region") or os.getenv("GOOGLE_CLOUD_LOCATION") or DEFAULT_REGION,
            metadata=metadata
        )
    except Exception as e:
        logger.error(f"Error loading system prompt with frontmatter: {e}")
        return fallback
