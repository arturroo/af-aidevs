"""
LLM backend: Native google-genai SDK (ADK) with Structured Output on Vertex AI.

TODO (Artur): Implement the tag_jobs_with_llm function using:
- genai.Client(vertexai=True, ...)
- Pydantic models for structured output
- Batch tagging (send all jobs in one request)
"""
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List
from enum import Enum


# TODO (Artur): Define your Pydantic models for the structured output here.
# Example skeleton:
#
# class PersonTag(BaseModel):
#     index: int
#     tags: list[str]
#
# class BatchTagResponse(BaseModel):
#     results: list[PersonTag]

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

# read system message once
system_message = open("prompts/system_message.md").read()

def tag_jobs_with_llm(
    people: list[dict],
    project_id: str,
    location: str,
    available_tags: dict[str, str],
) -> list[dict]:
    """
    Sends job descriptions to Gemini 2.5 Flash via Vertex AI in a single batch
    and returns the people list enriched with 'tags'.

    Args:
        people: List of person dicts (must contain 'job' key).
        project_id: GCP Project ID.
        location: GCP Region.
        available_tags: Dict of {tag_name: tag_description}.

    Returns:
        Same people list, but each dict now has a 'tags' key (list[str]).
    """

    # TODO (Artur): Initialize the Gemini client for Vertex AI
    # client = genai.Client(vertexai=True, project=project_id, location=location)
    # outer scope for cacheing
    ga_client = genai.Client(vertexai=True, project=project_id, location=location)    

    # TODO (Artur): Build a numbered list of job descriptions for batch tagging
    numbered_jobs = "\n".join(
        f"{i}. {p['job']}" for i, p in enumerate(people)
    )


    # TODO (Artur): Build the prompt with tag descriptions
    # tag_descriptions = "\n".join(
    #     f"- {name}: {desc}" for name, desc in available_tags.items()
    # )

    # TODO (Artur): Call the model using structured output
    # response = client.models.generate_content(
    #     model='gemini-2.5-flash',
    #     contents=f"... your prompt with {numbered_jobs} and {tag_descriptions} ...",
    #     config=types.GenerateContentConfig(
    #         response_mime_type="application/json",
    #         response_schema=BatchTagResponse,
    #     ),
    # )
    # job_description = people[0]["job"]
    # prompt = f"Job description: {job_description}"
    prompt = numbered_jobs

    response_config = types.GenerateContentConfig(
        system_instruction=system_message,
        temperature=0,
        top_p=0.1,
        max_output_tokens=8192,
        response_mime_type="application/json",
        response_schema=list[JobAnalysis]
    )

    response = ga_client.models.generate_content(
        # model="gemini-2.5-flash",
        model="gemini-3.1-flash-lite-preview",
        contents = prompt,
        config = response_config

    )

    print("RESPONSE TEXT:")
    print(response.text)

    print("RESPONSE PARSED:")
    print(response.parsed)

    print("RESPONSE USAGE_METADATA:")
    if response.usage_metadata:
        print(f"  Prompt tokens:     {response.usage_metadata.prompt_token_count}")
        print(f"  Candidates tokens: {response.usage_metadata.candidates_token_count}")
        print(f"  Total tokens:      {response.usage_metadata.total_token_count}")
    else:
        print("  None")

    print("RESPONSE PROMPT_FEEDBACK:")
    print(response.prompt_feedback)

    

    for result in response.parsed:
        # Extract the string value from each JobTag Enum using list comprehension
        people[result.index]["tags"] = [tag.value for tag in result.tags]

    return people
