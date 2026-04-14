from enum import Enum
from pydantic import BaseModel, Field

class JobTag(str, Enum):
    IT = "IT"
    TRANSPORT = "transport"
    EDUKACJA = "edukacja"
    MEDYCYNA = "medycyna"
    LUDZIE = "praca z ludźmi"
    POJAZDY = "praca z pojazdami"
    FIZYCZNA = "praca fizyczna"

class JobAnalysis(BaseModel):
    index: int = Field(
        description="Index of the job description in the input list."
    )
    reasoning: str = Field(
        description="Brief 1-sentence justification in Polish identifying key duties."
    )
    tags: list[JobTag] = Field(
        min_items=1,
        description="List of tags for the jobs, selected strictly according to system definitions."
    )

class JobAnalysisBatch(BaseModel):
    results: list[JobAnalysis] = Field(
        description="A list of job analysis records, one for each input job description."
    )
