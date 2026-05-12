from langchain_core.tools import tool
from datetime import datetime
from zoneinfo import ZoneInfo

@tool("get_current_date")
def get_current_date() -> str:
    """Returns the current date and time."""
    tz = ZoneInfo("Europe/Zurich")
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
