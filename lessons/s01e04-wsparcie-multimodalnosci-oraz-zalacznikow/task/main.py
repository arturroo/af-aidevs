import os
import argparse
import asyncio
import json
import httpx
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Backend specific imports
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from google import genai
from google.genai import types

load_dotenv()

# Constants from environment
AIDEVS_API_KEY = os.getenv("AIDEVS_API_KEY")
AIDEVS_VERIFY = os.getenv("AIDEVS_VERIFY")
AIDEVS_DOC = os.getenv("AIDEVS_DOC") # To be filled in .env

# Model configuration
MODEL_NAME = "gemini-1.5-flash-001" # Or gemini-2.0-flash-lite-preview-02-05 as per latest standards

class TaskData(BaseModel):
    nadawca: str = "450202122"
    punkt_nadawczy: str = "Gdańsk"
    punkt_docelowy: str = "Żarnowiec"
    waga: int = 2800
    zawartosc: str = "kasety z paliwem do reaktora"
    uwagi: str = "brak"
    budget: int = 0

class DocumentProcessor:
    def __init__(self):
        self.cache = {}

    async def fetch_text_doc(self, filename: str) -> str:
        """Fetches a text/markdown document from the hub."""
        if filename in self.cache:
            return self.cache[filename]
        
        url = f"{AIDEVS_DOC}/{filename}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            content = response.text
            self.cache[filename] = content
            return content

    async def fetch_binary_doc(self, filename: str) -> bytes:
        """Fetches an image/binary document from the hub."""
        url = f"{AIDEVS_DOC}/{filename}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

# --- LangChain Implementation ---

class SPKAgent:
    def __init__(self):
        self.llm = ChatVertexAI(model_name=MODEL_NAME, temperature=0)
        self.processor = DocumentProcessor()
        self.knowledge_base = {}

    async def read_document(self, filename: str) -> str:
        """Read a markdown document from the documentation hub."""
        content = await self.processor.fetch_text_doc(filename)
        self.knowledge_base[filename] = content
        return content

    async def analyze_image_document(self, filename: str, query: str) -> str:
        """Analyze an image document from the hub using vision."""
        image_data = await self.processor.fetch_binary_doc(filename)
        # Here we would use the LLM with the image data
        # For now, this is a placeholder for the actual vision call
        return f"Vision Analysis of {filename}: [Details about routes/rules extracted from image]"

    def get_tools(self):
        @tool
        async def read_doc_tool(filename: str) -> str:
            """Fetches and returns the content of a markdown file from SPK documentation."""
            return await self.read_document(filename)

        @tool
        async def analyze_img_tool(filename: str, query: str) -> str:
            """Uses vision to extract information from an image file in SPK documentation."""
            return await self.analyze_image_document(filename, query)

        return [read_doc_tool, analyze_img_tool]

async def run_langchain_logic():
    print("Initializing LangChain Agent Loop...")
    agent_handler = SPKAgent()
    tools = agent_handler.get_tools()
    llm_with_tools = agent_handler.llm.bind_tools(tools)
    
    system_msg = SystemMessage(content="""
    You are an expert logistics coordinator for the System Przesyłek Konduktorskich (SPK).
    Your goal is to fill out a transport declaration for a critical shipment.
    
    SHIPMENT DATA:
    - Nadawca: 450202122
    - Punkt nadawczy: Gdańsk
    - Punkt docelowy: Żarnowiec
    - Waga: 2800 kg
    - Zawartość: kasety z paliwem do reaktora
    - Uwagi: brak
    - Budget: 0 PP
    
    STEPS:
    1. Start by reading 'index.md' to understand the documentation structure.
    2. Recursively explore linked documents and images to find:
       - The correct route code for Gdańsk -> Żarnowiec.
       - The category (A-E) that allows for a 0 PP fee for this shipment.
       - The exact template for the declaration (found in one of the appendices).
    3. HINT: Critical information might be hidden in **HTML `<head>` tags**, document metadata, or "removed" files. Pay close attention to any HTML files you encounter.
    4. Once you have all the information, generate the final declaration string.
    
    IMPORTANT: The declaration must match the template exactly, including all separators and formatting.
    """)

    messages = [system_msg, HumanMessage(content="Start the discovery process and generate the declaration.")]
    
    # Simple loop simulation
    for i in range(10): # Limit iterations
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)
        
        if not response.tool_calls:
            print("\n--- Final Declaration Proposal ---\n")
            print(response.content)
            break
        
        for tool_call in response.tool_calls:
            # Execute tool logic here (mapping tool_call['name'] to actual functions)
            # This part needs actual tool execution plumbing
            print(f"Agent calls tool: {tool_call['name']} with {tool_call['args']}")
            # Placeholder for tool output
            tool_msg = ToolMessage(content="[Tool Output Placeholder]", tool_call_id=tool_call['id'])
            messages.append(tool_msg)

# --- Vertex AI GenAI SDK (ADK) Implementation ---

async def run_adk_logic():
    print("Running with Vertex AI SDK (ADK) backend...")
    client = genai.Client(vertexai=True, location="us-central1")
    # TODO: Implement equivalent logic using google-genai SDK
    pass

async def main():
    parser = argparse.ArgumentParser(description="S01E04 Task Boilerplate")
    parser.add_argument("--backend", choices=["langchain", "genai"], default="langchain", 
                        help="Framework choice (default: langchain)")
    args = parser.parse_args()

    if args.backend == "langchain":
        await run_langchain_logic()
    else:
        await run_adk_logic()

if __name__ == "__main__":
    asyncio.run(main())
