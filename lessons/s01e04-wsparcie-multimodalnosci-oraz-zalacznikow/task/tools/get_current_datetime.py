from langchain_core.tools import tool
from datetime import datetime
from zoneinfo import ZoneInfo
from schemas import GetDateInput, GetDateOutput

ZURICH_TZ = ZoneInfo("Europe/Zurich")

@tool("get_current_datetime", args_schema=GetDateInput)
def get_current_datetime(reasoning: str) -> GetDateOutput:
    """Returns the current date and time in Europe/Zurich. 
    Use this to contextualize your findings or when files refer to 'today' or relative dates.
    """
    now = datetime.now(ZURICH_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return GetDateOutput(
        current_date=now,
        hint="Use this date to determine if transport rules or route exclusions are still valid."
    )
