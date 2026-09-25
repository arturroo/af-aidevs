# Business Requirements Document (BRD) - S04E05: foodwarehouse

## Overview
The objective of this task (`foodwarehouse`) is to reprogram the automated distribution system of Siegfried's central warehouses to deliver critical food, water, and tools to eight starving regional settlements (Opalino, Domatowo, Brudzewo, Darzlubie, Celbowo, Mechowo, Puck, Karlinkowo). According to Azazel's intelligence, Siegfried's automated transporters are not tracked by the "OKO" surveillance grid, allowing supplies to be redirected completely undetected if valid warehouse orders are injected.

The warehouse management system exposes a central JSON-RPC-like interface via Centrala's verification endpoint (`$AIDEVS_API_VERIFY`). To execute the mission, the system must:
1. Inspect the warehouse database (SQLite) in read-only mode to discover destination codes, authorized order creators, and authorization rules.
2. Ingest municipal resource requirements from `$AIDEVS_FOOD4CITIES_URL`.
3. Generate valid cryptographic signatures (SHA1) for each order using the warehouse's `signatureGenerator` tool.
4. Create exactly one order per settlement with valid `title`, `creatorID`, `destination`, and `signature`.
5. Populate each order with the exact requested commodities and quantities using batch mode.
6. Verify the distribution via `tool: "done"` to receive the Centrala verification flag.

---

## Requirements

### Functional Requirements

1. **Bootstrap & Discovery (`tool: "help"`):**
   - The service issues an initial `tool: "help"` command to Centrala via `$AIDEVS_API_VERIFY` to inspect schema definitions, exact field requirements, and tool specifications:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "foodwarehouse",
       "answer": {
         "tool": "help"
       }
     }
     ```

2. **Database Reconnaissance (`tool: "database"`):**
   - Query the read-only SQLite database to discover tables and schemas:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "foodwarehouse",
       "answer": {
         "tool": "database",
         "query": "show tables"
       }
     }
     ```
   - Retrieve table schemas using standard SQLite queries (e.g. `PRAGMA table_info(<table>)` or `SELECT sql FROM sqlite_master WHERE type='table'`).
   - Query municipal and personnel records to map:
     - Each participating city name to its warehouse `destination` code.
     - Authorized warehouse creators (`creatorID` and related user attributes required for signature generation).

3. **Municipal Demand Ingestion:**
   - Download the target demand JSON from `$AIDEVS_FOOD4CITIES_URL`.
   - The payload defines 8 settlements and their exact item shortages:
     - `opalino`: `{"chleb": 45, "woda": 120, "mlotek": 6}`
     - `domatowo`: `{"makaron": 60, "woda": 150, "lopata": 8}`
     - `brudzewo`: `{"ryz": 55, "woda": 140, "wiertarka": 5}`
     - `darzlubie`: `{"wolowina": 25, "woda": 130, "kilof": 7}`
     - `celbowo`: `{"kurczak": 40, "woda": 125, "mlotek": 6}`
     - `mechowo`: `{"ziemniaki": 100, "kapusta": 70, "marchew": 65, "woda": 165, "lopata": 9}`
     - `puck`: `{"chleb": 50, "ryz": 45, "woda": 175, "wiertarka": 7}`
     - `karlinkowo`: `{"makaron": 52, "wolowina": 22, "ziemniaki": 95, "woda": 155, "kilof": 6}`

4. **Cryptographic Authorization & Signature Generation (`tool: "signatureGenerator"`):**
   - Obtain a valid SHA1 security signature for each order using the authorized creator's credentials from the database.
   - Verify input parameters required by `signatureGenerator` via `tool: "help"` or schema inspection.

5. **State Reset & Idempotency (`tool: "reset"`):**
   - Prior to creating orders (or in case of execution failure/dirty state), issue `tool: "reset"` to restore orders to the initial clean state:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "foodwarehouse",
       "answer": {
         "tool": "reset"
       }
     }
     ```

6. **Order Creation (`tool: "orders"`, `action: "create"`):**
   - Create exactly one order for each of the 8 cities:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "foodwarehouse",
       "answer": {
         "tool": "orders",
         "action": "create",
         "title": "Dostawa dla <NazwaMiasta>",
         "creatorID": 2,
         "destination": "<destination_code>",
         "signature": "<sha1_signature>"
       }
     }
     ```
   - Store the returned order ID (`id`) for each city.

7. **Batch Item Population (`tool: "orders"`, `action: "append"`):**
   - Populate each order with all required commodities in a single batch call using the dictionary format:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "foodwarehouse",
       "answer": {
         "tool": "orders",
         "action": "append",
         "id": "<order_id>",
         "items": {
           "chleb": 45,
           "woda": 120,
           "mlotek": 6
         }
       }
     }
     ```
   - Exact amounts must match `food4cities.json` with zero surplus and zero deficit.

8. **Completion Audit & Flag Retrieval (`tool: "done"`):**
   - Once all 8 orders are created and populated, dispatch final verification:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "foodwarehouse",
       "answer": {
         "tool": "done"
       }
     }
     ```
   - Centrala evaluates order completeness, destination codes, item quantities, and signatures, returning the verification flag `{FLG:...}`.

---

## System & Token Constraints

- **Order Count Cardinality:** Exactly 8 orders (one per city in `$AIDEVS_FOOD4CITIES_URL`). Extra or missing orders fail validation.
- **Quantity Accuracy:** Zero tolerance for item count discrepancies (`Bez braków i bez nadmiarów`). Note that appending to an existing item increments its count.
- **Read-Only Database Constraints:** Database access is strictly read-only (`SELECT`, `PRAGMA`). Write operations (`INSERT`, `UPDATE`, `DROP`) are forbidden and rejected by Centrala.
- **Roundtrip Optimization:** Batch appending (`action: "append"` with dictionary `items`) should be favored over individual item additions to prevent connection throttling and latency overhead.
- **Dual Framework Implementation:** In accordance with repository standards, the solution must provide feature parity across both **LangChain** (`langchain==1.2.15`) and **Google ADK** (`google-adk==1.33.0`) agent backends using Vertex AI Gemini 3.8 Flash (`gemini-3.8-flash`).

---

## Data Inputs & External Resources

| Resource | Environment Variable / Source | Purpose |
| :--- | :--- | :--- |
| Centrala Verification API | `$AIDEVS_API_VERIFY` | Primary API gateway for tool execution (`help`, `database`, `orders`, `signatureGenerator`, `reset`, `done`). |
| Centrala API Key | `$AIDEVS_API_KEY` | Authentication credential for all Centrala requests. |
| City Demand Manifest | `$AIDEVS_FOOD4CITIES_URL` | JSON manifest detailing target cities and their resource requirements. |
| Warehouse SQLite Database | Via `tool: "database"` | Read-only remote database providing city destination codes and user credentials. |

---

## API Integration & Schema Specifications

### Envelope Format
All interactions with Centrala use `POST $AIDEVS_API_VERIFY` with:
```json
{
  "apikey": "<api_key>",
  "task": "foodwarehouse",
  "answer": {
    "tool": "<tool_name>",
    "<parameter>": "<value>"
  }
}
```

### Supported Tools Summary

| Tool | Action / Parameter | Expected Response / Effect |
| :--- | :--- | :--- |
| `help` | None | Returns API documentation and tool schemas. |
| `reset` | None | Resets warehouse orders to clean state. |
| `database` | `query: "<SQL_STATEMENT>"` | Executes read-only query against warehouse SQLite database; returns rows/schema. |
| `signatureGenerator` | Creator parameters | Generates SHA1 authorization signature for order creation. |
| `orders` | `action: "get"` | Lists existing orders and their statuses. |
| `orders` | `action: "create"`, `title`, `creatorID`, `destination`, `signature` | Creates new order, returns order `id`. |
| `orders` | `action: "append"`, `id`, `items: {<name>: <count>}` | Batch-appends commodities to specified order. |
| `done` | None | Evaluates final state; returns success status and `{FLG:...}`. |

---

## Security & Environment Setup

The following environment variables are required in `.env` (local) and Secret Manager (Cloud Run):

| Variable Name | Description |
| :--- | :--- |
| `AIDEVS_API_KEY` | Course API authentication key. |
| `AIDEVS_API_VERIFY` | Centrala verification endpoint (`https://hub.ag3nts.org/verify`). |
| `AIDEVS_FOOD4CITIES_URL` | URL to `food4cities.json` (`https://hub.ag3nts.org/dane/food4cities.json`). |
| `GOOGLE_CLOUD_PROJECT` | GCP Project ID (`af-aidevs`). |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI model location (`global`). |

---

## Acceptance & Verification Criteria

1. **Database Schema Understanding:** The service accurately discovers table schemas, maps all 8 cities to their respective `destination` codes, and identifies valid `creatorID`(s).
2. **Signature Validity:** Signatures generated via `signatureGenerator` pass Centrala validation for all created orders.
3. **Exact Order Matching:** Exactly 8 orders are created, corresponding 1:1 with cities in `food4cities.json`.
4. **Commodity Precision:** Every order contains the exact item names and quantities specified in the demand manifest.
5. **Flag Capture:** Centrala validates the mission upon receiving `tool: "done"` and issues the verification flag `{FLG:...}`.
6. **Dual Agent Framework:** Both LangChain and Google ADK backends successfully execute the automated pipeline via CLI (`--backend langchain` and `--backend adk`) and Cloud Run HTTP endpoints.
