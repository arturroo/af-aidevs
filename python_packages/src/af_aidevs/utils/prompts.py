import os
import logging
import frontmatter
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

logger = logging.getLogger("utils.prompts")

class SystemPromptConfig(BaseModel):
    """Schema for system prompt and its associated metadata."""
    model_config = {'protected_namespaces': ()}
    
    system_prompt: str = Field(..., description="The actual system instruction text.")
    model: str = Field("gemini-3-flash-preview", description="The LLM model ID to use.")
    temperature: float = Field(0.1, description="The sampling temperature.")
    model_region: Optional[str] = Field(None, description="The GCP region for the model (e.g., europe-west6).")
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
        system_prompt="You are a helpful assistant.",
        model="gemini-3-flash-preview",
        temperature=0.1,
        model_region=os.getenv("GOOGLE_CLOUD_LOCATION") or "europe-west6"
    )
    
    if not prompt_path.exists():
        logger.warning(f"{filename} not found in {base_dir}, using fallback.")
        return fallback
    
    try:
        post = frontmatter.load(prompt_path)
        metadata = post.metadata
        
        return SystemPromptConfig(
            system_prompt=post.content.strip(),
            model=metadata.get("model", "gemini-3-flash-preview"),
            temperature=float(metadata.get("temperature", 0.1)),
            model_region=metadata.get("location") or metadata.get("model_region") or os.getenv("GOOGLE_CLOUD_LOCATION") or "europe-west6",
            metadata=metadata
        )
    except Exception as e:
        logger.error(f"Error loading system prompt with frontmatter: {e}")
        return fallback
