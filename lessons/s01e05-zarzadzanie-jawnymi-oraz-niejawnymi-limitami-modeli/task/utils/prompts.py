import frontmatter
from pathlib import Path

class PromptConfig:
    def __init__(self, system_prompt: str, model: str, model_region: str, temperature: float):
        self.system_prompt = system_prompt
        self.model = model
        self.model_region = model_region
        self.temperature = temperature

def load_system_prompt(base_dir: Path) -> PromptConfig:
    prompt_file = base_dir / "system_prompt.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"system_prompt.md not found in {base_dir}")
    
    post = frontmatter.load(prompt_file)
    system_prompt = post.content
    model = post.metadata.get("model", "gemini-3.1-flash-lite-preview")
    model_region = post.metadata.get("model_region", "global")
    temperature = post.metadata.get("temperature", 0.2)
    
    return PromptConfig(system_prompt, model, model_region, temperature)
