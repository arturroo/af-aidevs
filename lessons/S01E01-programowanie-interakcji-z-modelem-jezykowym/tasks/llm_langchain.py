"""
LLM backend: LangChain with ChatVertexAI and Structured Output.

TODO (Artur): Implement the tag_jobs_with_llm function using:
- ChatVertexAI(model_name="gemini-2.5-flash", ...)
- llm.with_structured_output(YourPydanticModel)
- Batch tagging (send all jobs in one request)
"""
from langchain_google_vertexai import ChatVertexAI
from pydantic import BaseModel


# TODO (Artur): Define your Pydantic models for the structured output here.
# Example skeleton:
#
# class PersonTag(BaseModel):
#     index: int
#     tags: list[str]
#
# class BatchTagResponse(BaseModel):
#     results: list[PersonTag]


def tag_jobs_with_llm(
    people: list[dict],
    project_id: str,
    location: str,
    available_tags: dict[str, str],
) -> list[dict]:
    """
    Sends job descriptions to Gemini 2.5 Flash via LangChain in a single batch
    and returns the people list enriched with 'tags'.

    Args:
        people: List of person dicts (must contain 'job' key).
        project_id: GCP Project ID.
        location: GCP Region.
        available_tags: Dict of {tag_name: tag_description}.

    Returns:
        Same people list, but each dict now has a 'tags' key (list[str]).
    """

    # TODO (Artur): Initialize the LangChain ChatVertexAI client
    # llm = ChatVertexAI(
    #     model_name="gemini-2.5-flash",
    #     project=project_id,
    #     location=location,
    # )

    # TODO (Artur): Bind structured output to the model
    # structured_llm = llm.with_structured_output(BatchTagResponse)

    # TODO (Artur): Build the prompt with numbered jobs and tag descriptions
    # numbered_jobs = "\n".join(
    #     f"{i}. {p['job']}" for i, p in enumerate(people)
    # )
    # tag_descriptions = "\n".join(
    #     f"- {name}: {desc}" for name, desc in available_tags.items()
    # )

    # TODO (Artur): Call the model
    # response = structured_llm.invoke(
    #     f"... your prompt with {numbered_jobs} and {tag_descriptions} ..."
    # )

    # TODO (Artur): Map the returned tags back onto each person dict
    # for result in response.results:
    #     people[result.index]["tags"] = result.tags

    return people
