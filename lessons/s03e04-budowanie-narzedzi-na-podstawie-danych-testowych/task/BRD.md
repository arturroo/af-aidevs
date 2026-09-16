# Business Requirements Document (BRD) - S03E04: negotiations

## Overview
The goal of this task (`negotiations`) is to design, implement, and expose one or two HTTP tool endpoints that will be registered with the Centrala automated agent system. Centrala's autonomous agent needs to locate safe haven cities that currently have in stock **all three** required components needed to assemble and commission a wind turbine to supply power to the resistance base.

Centrala's agent sends tool requests in natural language (unstructured parameters). The tool must parse or search the inventory dataset, resolve city availability, and return a concise response within strict byte and step constraints, allowing Centrala's agent to identify the candidate cities and negotiate purchases autonomously.

## Requirements

### Functional Requirements
1. **Tool Definition & Exposure:**
   - Expose either 1 unified tool or up to 2 specialized HTTP POST tools reachable over the public internet (or via tunnel/Cloud Run).
   - Each tool must be clearly described so that Centrala's agent understands its purpose, schema, and what natural language queries to pass into `params`.
2. **Centrala Agent Interaction Protocol:**
   - Centrala's agent sends HTTP POST requests to the registered tool URL with JSON body:
     ```json
     {
       "params": "natural language string query from agent"
     }
     ```
   - The tool endpoint MUST respond with JSON:
     ```json
     {
       "output": "concise answer string for the agent"
     }
     ```
3. **Natural Language Query Interpretation:**
   - Queries from Centrala's agent will arrive in natural language (e.g. `"potrzebuję kabla długości 10 metrów"`, descriptive part queries, or city/item availability questions).
   - The tool must map natural language descriptions to items in the database and cross-reference which cities stock them.
4. **City & Inventory Resolution:**
   - Grounded strictly in the three provided CSV datasets:
     - `cities.csv`: `name,code` (e.g. `Warszawa,A7K3QX`)
     - `items.csv`: `name,code` (e.g. `Rezystor metalizowany 1 ohm...,BWST28`)
     - `connections.csv`: `itemCode,cityCode` (mapping item availability to city codes)
   - The agent requires identifying cities that have **all 3** requested turbine components simultaneously.
5. **Registration & Asynchronous Verification:**
   - Register the tool(s) by sending an initial submission payload to the `$AIDEVS_API_VERIFY` endpoint:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "negotiations",
       "answer": {
         "tools": [
           {
             "URL": "https://<tool-host>/api/tool1",
             "description": "<Clear description of tool 1 purpose and expected params>"
           }
         ]
       }
     }
     ```
   - Once submitted, Centrala's agent starts querying the registered endpoint(s).
   - Polling / Status Check: Wait at least 30-60 seconds for Centrala's agent to finish its execution (up to 10 steps), then poll `$AIDEVS_API_VERIFY` with:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "negotiations",
       "answer": {
         "action": "check"
       }
     }
     ```
   - Extract and verify the returned course flag upon successful completion.

### Special Exceptions & Guardrails
- **Byte Size Constraint:** Tool responses (`output`) MUST be between **4 bytes** and **500 bytes** inclusive:
  `4 <= len(output.encode('utf-8')) <= 500`. Exceeding 500 bytes causes an immediate rejection/failure from Centrala.
- **Step Limit Constraint:** The Centrala agent is allocated a maximum of **10 steps** to complete its discovery. Descriptions and tool outputs must be efficient, progressive, and prevent redundant iterations.
- **Maximum Tool Count:** At most **2 tools** can be registered in the `tools` array.
- **Zero-Drop Policy:** If a tool returns an empty response or fails to respond, Centrala's agent aborts execution immediately.

## System & Token Constraints
- **Response Size:** Maximum 500 bytes in the `output` string.
- **Centrala Execution Budget:** Maximum 10 interaction steps.
- **Model Standard:** Primary model used for semantic matching / query interpretation is **Gemini 3.8 Flash** (`gemini-3.8-flash`) on Vertex AI with `thinking_level="low"`.
- **Latency:** Keep tool response times low (< 2-3 seconds) to prevent Centrala agent timeouts during multi-turn calls.

## Data Input & External Resources
- Inventory & city database files provided at `$AIDEVS_S03E04_DATA_URL`:
  - `cities.csv`: List of available survivor cities and their unique 6-character codes.
  - `items.csv`: Catalog of hardware items/components and their unique codes.
  - `connections.csv`: Many-to-many relationship mapping item codes to city codes.
- All CSV data should be ingested and pre-indexed (e.g. SQLite, Pandas, or vector/semantic search) for fast sub-second lookups.

## API Integration

### 1. Verification Endpoint (`$AIDEVS_API_VERIFY`)
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`
- **Initial Registration Payload:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "negotiations",
    "answer": {
      "tools": [
        {
          "URL": "https://<public-url>/<tool-endpoint>",
          "description": "Description of functionality and query format"
        }
      ]
    }
  }
  ```
- **Check Status Payload:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "negotiations",
    "answer": {
      "action": "check"
    }
  }
  ```

### 2. Tool Endpoint(s) Hosted by Microservice
- **Method:** `POST`
- **Input Schema:**
  ```json
  {
    "params": "string"
  }
  ```
- **Output Schema:**
  ```json
  {
    "output": "string (4 to 500 bytes)"
  }
  ```

## Security & Environment Setup
All secret tokens and external URLs MUST be configured through environment variables:
- `AIDEVS_API_KEY`: Course authorization key.
- `AIDEVS_API_VERIFY`: Verification endpoint URL (`https://.../verify`).
- `AIDEVS_S03E04_DATA_URL`: Base URL hosting the lesson CSV resources.
- `CENTRAL_PUBLIC_URL` / `TOOL_PUBLIC_URL`: Publicly accessible URL for the deployed Cloud Run service or local ngrok tunnel.
- `GOOGLE_CLOUD_PROJECT`: GCP project ID (`af-aidevs`).
- `GOOGLE_CLOUD_LOCATION`: Vertex AI location (`global` or default region).

## Verification & Acceptance Criteria
1. Tool service responds to test `POST` requests with valid JSON (`{"output": "..."}`) with byte lengths between 4 and 500 bytes.
2. Given natural language queries for turbine parts, the tool accurately identifies the matching items and resolves which cities stock them.
3. Centrala agent receives informative answers and converges to the correct set of cities within 10 steps.
4. Asynchronous verification check (`{"action": "check"}`) returns code 0 and the secret course flag.
