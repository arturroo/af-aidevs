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
    # numbered_jobs = "\n".join(
    #     f"{i}. {p['job']}" for i, p in enumerate(people)
    # )


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
    job_description = people[0]["job"]
    prompt = f"Job description: {job_description}"

    response_config = types.GenerateContentConfig(
        system_instruction=system_message,
        temperature=0,
        top_p=0.1,
        max_output_tokens=1024,
        response_mime_type="application/json",
        response_schema=JobAnalysis
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
    print(response.usage_metadata)

    print("RESPONSE PROMPT_FEEDBACK:")
    print(response.prompt_feedback)

    # inline batch request
    # In the free AI Studio (developer API), the Batch API supports sending inline JSON requests and receiving inline JSON arrays back.
    # In Vertex AI (enterprise API, vertexai=True), the Asynchronous Batch API is designed for massive scale (millions of rows). 
    # Because of this enterprise design, Vertex AI strictly prohibits sending the data "inline" in the API call. 
    # It forces you to provide a gcs_uri (Google Cloud Storage) or bigquery_uri for both the input data and the output destination.

    print("\n\n--- Inline batch request ---")
    inline_requests = []
    for i, person in enumerate(people):
        job_description = person["job"]
        prompt = f"{i} Job description: {job_description}"

        inline_requests.append(
            {
                'contents': [{
                    'parts': [{'text': prompt}],
                    'role': 'user'
                }],
                'config': {
                    'response_mime_type': 'application/json',
                    'response_schema': list[JobAnalysis]
                }
            },
        )
    inline_batch_job = ga_client.batches.create(
        model="gemini-3.1-flash-lite-preview",
        src=inline_requests,
        config={
            'display_name': "structured-output-job-1"
        }
    )
    print(f"Created batch job: {inline_batch_job.name}")

    job_name = inline_batch_job.name
    batch_job = ga_client.batches.get(name=job_name)

    completed_states = set([
        'JOB_STATE_SUCCEEDED',
        'JOB_STATE_FAILED',
        'JOB_STATE_CANCELLED',
        'JOB_STATE_EXPIRED',
    ])

    print(f"Polling status for job: {job_name}")
    batch_job = ga_client.batches.get(name=job_name) # Initial get
    while batch_job.state.name not in completed_states:
        print(f"Current state: {batch_job.state.name}")
        time.sleep(5) 
        batch_job = ga_client.batches.get(name=job_name)

    print(f"Job finished with state: {batch_job.state.name}")
    if batch_job.state.name == 'JOB_STATE_FAILED':
        print(f"Error: {batch_job.error}")

    
    if batch_job.state.name == 'JOB_STATE_SUCCEEDED':
        
        # If batch job was created with a file
        if batch_job.dest and batch_job.dest.file_name:
            # Results are in a file
            result_file_name = batch_job.dest.file_name
            print(f"Results are in file: {result_file_name}")
    
            print("Downloading result file content...")
            file_content = ga_client.files.download(file=result_file_name)
            # Process file_content (bytes) as needed
            print(file_content.decode('utf-8'))
    
        # If batch job was created with inline request
        # (for embeddings, use batch_job.dest.inlined_embed_content_responses)
        elif batch_job.dest and batch_job.dest.inlined_responses:
            # Results are inline
            print("Results are inline:")
            for i, inline_response in enumerate(batch_job.dest.inlined_responses):
                print(f"Response {i+1}:")
                if inline_response.response:
                    # Accessing response, structure may vary.
                    try:
                        print(inline_response.response.text)
                    except AttributeError:
                        print(inline_response.response) # Fallback
                elif inline_response.error:
                    print(f"Error: {inline_response.error}")
        else:
            print("No results found (neither file nor inline).")
    else:
        print(f"Job did not succeed. Final state: {batch_job.state.name}")
        if batch_job.error:
            print(f"Error: {batch_job.error}")





    # print("RESPONSE TEXT:")
    # print(response.text)
    # print("RESPONSE PARSED:")
    # print(response.parsed)
    # print("RESPONSE USAGE_METADATA:")
    # print(response.usage_metadata)
    # print("RESPONSE PROMPT_FEEDBACK:")
    # print(response.prompt_feedback)

    # TODO (Artur): Map the returned tags back onto each person dict
    # for result in response.parsed.results:
    #     people[result.index]["tags"] = result.tags

    return people
