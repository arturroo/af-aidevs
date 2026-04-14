"""
LLM backend: LangChain with ChatVertexAI and Structured Output.
"""
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_vertexai import ChatVertexAI
from typing import List
from data_models import JobAnalysis, JobAnalysisBatch

# read system message once
system_message_content = open("prompts/system_message.md").read()

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

    # Initialize the LangChain ChatVertexAI client
    llm = ChatVertexAI(
        model_name="gemini-3.1-flash-lite-preview",
        project=project_id,
        location=location,
        temperature=0,
        top_p=0.1,
        max_output_tokens=8192,
    )

    # Bind structured output to the model using the Batch wrapper, and include raw response to get metadata
    structured_llm = llm.with_structured_output(JobAnalysisBatch, include_raw=True)

    # Build the prompt with numbered jobs
    numbered_jobs = "\n".join(
        f"{i}. {p['job']}" for i, p in enumerate(people)
    )

    # Call the model
    print(f"Sending batch request with {len(people)} jobs via LangChain...")
    response_data = structured_llm.invoke([
        SystemMessage(content=system_message_content),
        HumanMessage(content=numbered_jobs)
    ])

    batch_response = response_data["parsed"]
    raw_response = response_data["raw"]

    print("RESPONSE PARSED:")
    print(batch_response)


    # Map the returned tags back onto each person dict
    for result in batch_response.results:
        # Extract the string value from each JobTag Enum using list comprehension
        people[result.index]["tags"] = [tag.value for tag in result.tags]

    print("RESPONSE USAGE_METADATA:")
    if hasattr(raw_response, 'usage_metadata') and raw_response.usage_metadata:
        usage = raw_response.usage_metadata
        print(f"  Prompt tokens:     {usage.get('input_tokens', 'N/A')}")
        print(f"  Candidates tokens: {usage.get('output_tokens', 'N/A')}")
        print(f"  Total tokens:      {usage.get('total_tokens', 'N/A')}")
    else:
        print("  None")

    return people
