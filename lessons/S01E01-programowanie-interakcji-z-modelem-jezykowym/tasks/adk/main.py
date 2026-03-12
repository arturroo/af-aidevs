"""
AI_Devs S01E01 - People tagging task
Uses native google-genai SDK with Structured Output on Vertex AI.
"""
import csv
import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel
import requests

load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or "YOUR_PROJECT_ID"
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION") or "europe-west6"
PERSONAL_API_KEY = os.getenv("PERSONAL_API_KEY")

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "people.csv")
VERIFY_URL = "https://hub.ag3nts.org/verify"

# Available tags for classification (add descriptions to help the model)
AVAILABLE_TAGS = {
    "transport": "Transport, logistics, driving, delivery, shipping, fleet management",
    # TODO: Add remaining tags from the task description here
}


# ---------------------------------------------------------------------------
# Step 1: Load & filter CSV
# ---------------------------------------------------------------------------
def load_and_filter_people(path: str) -> list[dict]:
    """
    Loads people.csv and filters for:
    - gender == 'M'
    - birthPlace == 'Grudziądz'
    - age between 20 and 40 in 2026 (born between 1986 and 2006 inclusive)
    """
    filtered = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["gender"] != "M":
                continue
            if row["birthPlace"] != "Grudziądz":
                continue

            birth_year = int(row["birthDate"].split("-")[0])
            age_in_2026 = 2026 - birth_year
            if not (20 <= age_in_2026 <= 40):
                continue

            filtered.append({
                "name": row["name"],
                "surname": row["surname"],
                "gender": row["gender"],
                "born": birth_year,
                "city": row["birthPlace"],
                "job": row["job"],
            })

    print(f"Filtered {len(filtered)} people (male, Grudziądz, age 20-40).")
    return filtered


# ---------------------------------------------------------------------------
# Step 2: Tag jobs using LLM with Structured Output (batch tagging)
# ---------------------------------------------------------------------------

# TODO (Artur): Define your Pydantic model for the structured output here.
# Example skeleton:
#
# class PersonTag(BaseModel):
#     index: int
#     tags: list[str]
#
# class BatchTagResponse(BaseModel):
#     results: list[PersonTag]


def tag_jobs_with_llm(people: list[dict]) -> list[dict]:
    """
    Sends job descriptions to Gemini 2.5 Flash via Vertex AI in a single batch
    and returns the people list enriched with 'tags'.
    """

    # TODO (Artur): Initialize the Gemini client for Vertex AI
    # client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

    # TODO (Artur): Build a numbered list of job descriptions for batch tagging
    # Example:
    # numbered_jobs = "\n".join(
    #     f"{i}. {p['job']}" for i, p in enumerate(people)
    # )

    # TODO (Artur): Build the prompt with tag descriptions and call the model
    # using structured output (response_schema=BatchTagResponse)

    # TODO (Artur): Map the returned tags back onto each person dict
    # for result in response.parsed.results:
    #     people[result.index]["tags"] = result.tags

    return people


# ---------------------------------------------------------------------------
# Step 3: Filter for transport tag only
# ---------------------------------------------------------------------------
def filter_transport(people: list[dict]) -> list[dict]:
    """Keeps only people who have 'transport' in their tags."""
    return [p for p in people if "transport" in p.get("tags", [])]


# ---------------------------------------------------------------------------
# Step 4: Submit answer
# ---------------------------------------------------------------------------
def submit_answer(people: list[dict]):
    """Sends the final answer to the verification endpoint."""
    # Remove the 'job' field before sending - it's not part of the answer schema
    answer = []
    for p in people:
        answer.append({
            "name": p["name"],
            "surname": p["surname"],
            "gender": p["gender"],
            "born": p["born"],
            "city": p["city"],
            "tags": p["tags"],
        })

    payload = {
        "apikey": PERSONAL_API_KEY,
        "task": "people",
        "answer": answer,
    }

    print(f"\nSubmitting {len(answer)} people to {VERIFY_URL}...")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    response = requests.post(VERIFY_URL, json=payload)
    print(f"\nStatus: {response.status_code}")
    print(f"Response: {response.text}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if not PERSONAL_API_KEY:
        print("Error: PERSONAL_API_KEY not found in .env")
        return

    # Step 1: Load & filter
    people = load_and_filter_people(DATA_PATH)
    if not people:
        print("No people matched the filter criteria.")
        return

    # Print filtered people for review
    print("\nFiltered people:")
    for i, p in enumerate(people):
        print(f"  {i}. {p['name']} {p['surname']} (born {p['born']}): {p['job'][:80]}...")

    # Step 2: Tag with LLM
    people = tag_jobs_with_llm(people)

    # Step 3: Filter transport
    transport_people = filter_transport(people)
    print(f"\nFound {len(transport_people)} people with 'transport' tag.")

    # Step 4: Submit
    if transport_people:
        submit_answer(transport_people)
    else:
        print("No transport people found. Check your tagging logic.")


if __name__ == "__main__":
    main()
