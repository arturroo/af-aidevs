import os
import importlib
import logging
from pathlib import Path
from langchain_core.tools import tool
from schemas import DiscoverToolsInput, DiscoverToolsOutput

logger = logging.getLogger("tools.discover_tools")

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = BASE_DIR / "tools"

@tool("discover_tools", args_schema=DiscoverToolsInput)
def discover_tools(reasoning: str) -> dict:
    """Lists all specialized tools available for the current mission. 
    Use this at the beginning to understand your capabilities.
    """
    logger.info(f"==== TOOL DEBUG ==== discover_tools: Scanning {TOOLS_DIR}")
    tools_info = []
    
    if not TOOLS_DIR.exists():
        logger.error(f"==== TOOL DEBUG ==== discover_tools: TOOLS_DIR DOES NOT EXIST!")
        return DiscoverToolsOutput(available_tools=[], error="Tools directory not found.").model_dump()

    # We skip this file and __init__.py
    for file_path in TOOLS_DIR.glob("*.py"):
        if file_path.name in ["__init__.py", "discover_tools.py"]:
            continue
            
        module_name = f"tools.{file_path.stem}"
        try:
            # We don't use the cache here to be sure we get the latest
            module = importlib.import_module(module_name)
            tool_func = getattr(module, file_path.stem)
            
            # Extract name and description from the LangChain tool
            if hasattr(tool_func, "name"):
                logger.info(f"==== TOOL DEBUG ==== discover_tools: Found tool '{tool_func.name}'")
                tools_info.append({
                    "name": tool_func.name,
                    "description": tool_func.description if hasattr(tool_func, "description") else "No description available."
                })
        except Exception as e:
            logger.error(f"==== TOOL DEBUG ==== discover_tools: Failed to load {module_name}: {e}")
            continue

    result = DiscoverToolsOutput(
        available_tools=tools_info,
        hint="Now you can call any of the discovered tools. Remember to use 'list_local_files' to explore your data sandbox."
    )
    logger.info(f"==== TOOL DEBUG ==== discover_tools: Returning {len(tools_info)} tools.")
    return result.model_dump()
