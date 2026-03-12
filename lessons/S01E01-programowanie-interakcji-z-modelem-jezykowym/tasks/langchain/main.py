import os
from dotenv import load_dotenv
from langchain_google_vertexai import ChatVertexAI
from pydantic import BaseModel
import requests

load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or "YOUR_PROJECT_ID"
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION") or "europe-west6"

def fetch_lesson_data(api_key: str) -> str:
    """Fetches the lesson CSV/data using the provided API key."""
    # TODO: Implement the fetch logic based on the lesson URL
    pass

class LessonResponse(BaseModel):
    """The Pydantic schema for the structured format expected by the lesson."""
    # TODO: Define the exact fields required by the AI_Devs task here
    example_field: str

def main():
    personal_api_key = os.getenv("PERSONAL_API_KEY")
    if not personal_api_key:
        print("Error: PERSONAL_API_KEY not found in .env")
        return
        
    print("Fetching data...")
    # data = fetch_lesson_data(personal_api_key)
    
    # Initialize LangChain ChatVertexAI client
    # with_structured_output forces the model to return data matching the Pydantic schema
    llm = ChatVertexAI(
        model_name="gemini-2.5-flash", 
        project=PROJECT_ID, 
        location=LOCATION
    )
    structured_llm = llm.with_structured_output(LessonResponse)
    
    print("Sending to Gemini 2.5 Flash on Vertex AI (LangChain)...")
    
    # The invoke method directly returns the validated Pydantic object
    # response = structured_llm.invoke("Extract the information from this data: ...")
    
    # print(response.example_field)

if __name__ == "__main__":
    main()
