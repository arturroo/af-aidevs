# Business Requirements Document (BRD) - S04E04: filesystem

## Overview
The objective of this task (`filesystem`) is to structure and normalize unstructured trade notes belonging to Natan Rams into a clean, hierarchical virtual filesystem hosted on the Centrala platform. Natan, a survivor of the city bombings who previously coordinated barter trade across regional settlements, was rescued and brought to safety. To coordinate future regional logistics and relief without alerting Siegfried's "OKO" surveillance network, Centrala needs an accurate, organized digital knowledge repository of:
1. **Cities (`/miasta`)**: Participating settlements, including their exact resource shortages and demanded goods.
2. **Persons (`/osoby`)**: Key trade coordinators representing each settlement.
3. **Commodities (`/towary`)**: Goods available for barter and the settlements producing/supplying them.

The system communicates with Centrala via the verification endpoint (`$AIDEVS_API_VERIFY`) using task ID `"filesystem"`. After initializing, resetting, and populating the directory hierarchy with validated files, the agent executes `action: "done"` to trigger Centrala's automated compliance audit and capture the verification flag.

---

## Requirements

### Functional Requirements

1. **Bootstrap & Discovery (`action: "help"`):**
   - The system initiates operational discovery by dispatching an `action: "help"` command to Centrala at `$AIDEVS_API_VERIFY` using the payload:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "filesystem",
       "answer": {
         "action": "help"
       }
     }
     ```
   - The response details supported actions, parameter constraints, batch limitations, and path conventions.

2. **Clean State Initialization (`action: "reset"`):**
   - Before uploading new data, the service issues an `action: "reset"` command to ensure no orphan files or remnants from previous test runs persist:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "filesystem",
       "answer": {
         "action": "reset"
       }
     }
     ```

3. **Data Source Ingestion & Unpacking:**
   - Raw intelligence is provided as a compressed archive downloaded from `$AIDEVS_S04E04_NOTES_URL`.
   - The archive unpacks into three primary intelligence logs:
     - `ogloszenia.txt`: Bulletin board notices documenting urgent resource shortages across various settlements.
     - `rozmowy.txt`: Natan's journal records of direct phone conversations with municipal trade leaders.
     - `transakcje.txt`: Historical trade ledger recording executed sales between cities (`<CityA> -> <commodity> -> <CityB>`).

4. **Directory Structure & Naming Conventions:**
   - The virtual filesystem requires exactly three primary directories at the root level:
     - `/miasta`
     - `/osoby`
     - `/towary`
   - **ASCII & Diacritics Restriction:** No Polish diacritics (ą, ć, ę, ł, ń, ó, ś, ź, ż) are permitted in file paths, file names, or JSON string contents. All text must be transliterated to standard ASCII (e.g., `ł` -> `l`, `ó` -> `o`).

5. **Entity Specifications:**

   #### A. Settlements (`/miasta/<city>`)
   - **File Location:** `/miasta/<nazwa_miasta>` (nominative singular, lowercase ASCII, e.g. `/miasta/opalino`, `/miasta/domatowo`).
   - **File Content:** A JSON object mapping requested goods (keys in singular nominative ASCII) to their integer quantities (excluding units such as 'workow', 'kg', 'butelek', 'porcji'):
     ```json
     {
       "chleb": 45,
       "woda": 120,
       "mlotek": 6
     }
     ```
   - **Data Grounding (`ogloszenia.txt`):**
     - **Opalino:** 45 chleb, 120 woda, 6 mlotek
     - **Domatowo:** 60 makaron, 150 woda, 8 lopata
     - **Brudzewo:** 55 ryz, 140 woda, 5 wiertarka
     - **Darzlubie:** 25 wolowina, 130 woda, 7 kilof
     - **Celbowo:** 40 kurczak, 125 woda, 6 mlotek
     - **Mechowo:** 100 ziemniak (or ziemniaki), 70 kapusta, 65 marchew, 165 woda, 9 lopata
     - **Puck:** 50 chleb, 45 ryz, 175 woda, 7 wiertarka
     - **Karlinkowo:** 52 makaron, 22 wolowina, 95 ziemniak (or ziemniaki), 155 woda, 6 kilof

   #### B. Persons (`/osoby/<Person_Name>`)
   - **File Location:** `/osoby/<Firstname_Lastname>` using underscore instead of spaces, normalized ASCII without diacritics (e.g. `/osoby/Iga_Kapecka`, `/osoby/Rafal_Kisiel`).
   - **File Content:** Text describing the person and including a standard Markdown hyperlink pointing to the managed city's file path:
     - Format: `[NazwaMiasta](/miasta/nazwamiasta)`
     - Example: `Iga Kapecka zarządza miastem [Opalino](/miasta/opalino)`
   - **Data Grounding (`rozmowy.txt`):**
     - **Domatowo:** Natan Rams -> `/osoby/Natan_Rams` -> `[Domatowo](/miasta/domatowo)`
     - **Opalino:** Iga Kapecka -> `/osoby/Iga_Kapecka` -> `[Opalino](/miasta/opalino)`
     - **Brudzewo:** Rafal Kisiel -> `/osoby/Rafal_Kisiel` -> `[Brudzewo](/miasta/brudzewo)`
     - **Darzlubie:** Marta Frantz -> `/osoby/Marta_Frantz` -> `[Darzlubie](/miasta/darzlubie)`
     - **Celbowo:** Oskar Radtke -> `/osoby/Oskar_Radtke` -> `[Celbowo](/miasta/celbowo)`
     - **Mechowo:** Eliza Redmann -> `/osoby/Eliza_Redmann` -> `[Mechowo](/miasta/mechowo)`
     - **Puck:** Damian Kroll -> `/osoby/Damian_Kroll` -> `[Puck](/miasta/puck)`
     - **Karlinkowo:** Lena Konkel -> `/osoby/Lena_Konkel` -> `[Karlinkowo](/miasta/karlinkowo)`

   #### C. Commodities (`/towary/<commodity>`)
   - **File Location:** `/towary/<nazwa_towaru>` where filename is strictly in nominative singular, ASCII lowercase (e.g. `/towary/koparka`, `/towary/wiertarka`, `/towary/lopata`, `/towary/chleb`, `/towary/ziemniak`).
   - **File Content:** Standard Markdown hyperlink(s) pointing to the city (or cities) that offer/sell the commodity based on historical trade records.
   - **Data Grounding (`transakcje.txt` - Seller is Source City `<CityA> -> <commodity> -> <CityB>`):**
     - `chleb`: Offered by Domatowo, Celbowo, Brudzewo
     - `kapusta`: Offered by Celbowo
     - `kilof`: Offered by Puck, Mechowo, Celbowo
     - `kurczak`: Offered by Darzlubie
     - `lopata`: Offered by Brudzewo, Puck
     - `maka`: Offered by Brudzewo, Mechowo
     - `makaron`: Offered by Opalino
     - `marchew`: Offered by Puck
     - `mlotek`: Offered by Karlinkowo, Mechowo
     - `ryz`: Offered by Darzlubie, Opalino, Karlinkowo
     - `wiertarka`: Offered by Karlinkowo, Domatowo
     - `wolowina`: Offered by Opalino
     - `ziemniak` (or `ziemniaki`): Offered by Domatowo, Darzlubie

6. **Batch Mode Support:**
   - The Centrala API supports batch payload execution: multiple operations (`createFile`, `mkdir`, etc.) can be combined into a single JSON array under `answer: [...]`.
   - Batch mode must be supported to minimize network roundtrips and ensure atomic delivery.

7. **Verification & Audit (`action: "done"`):**
   - Once all files and directories are populated, dispatch `action: "done"`:
     ```json
     {
       "apikey": "$AIDEVS_API_KEY",
       "task": "filesystem",
       "answer": {
         "action": "done"
       }
     }
     ```
   - Capture Centrala's response and extract the verification flag (`{FLG:...}`).
   - Record execution telemetry and results to BigQuery dataset `s04e04`.

---

## System & Constraints

1. **Token & Latency Constraints:**
   - Use **Gemini 3.8 Flash** (`gemini-3.8-flash`) on **Vertex AI** (`GOOGLE_CLOUD_LOCATION=global`, `thinking_level="low"`).
   - Ingestion and parsing of the raw text logs can be performed deterministically or via LLM-assisted schema extraction. Batching file creation into 1–2 HTTP payloads eliminates API roundtrip bottlenecks.

2. **Error Handling & Resilience:**
   - Centrala API may reject malformed markdown links, invalid JSON syntax, non-ASCII characters, or missing directories.
   - The service must validate JSON payloads with Pydantic prior to dispatch.
   - Filesystem state can be inspected via `$AIDEVS_S04E04_FILESYSTEM_PREVIEW_URL` or via API actions.

3. **Security Constraints:**
   - **Zero Hardcoded External URLs:** Never include raw URLs in source code, markdown docs, or environment templates.
   - All external endpoints must be injected via environment variables:
     - Centrala Verify URL: `$AIDEVS_API_VERIFY`
     - Notes Archive URL: `$AIDEVS_S04E04_NOTES_URL`
     - Filesystem Preview URL: `$AIDEVS_S04E04_FILESYSTEM_PREVIEW_URL`
     - Centrala API Key: `$AIDEVS_API_KEY`

---

## External Resources & Data Inputs

| Resource Identifier | Description | Ingestion Method |
| :--- | :--- | :--- |
| `$AIDEVS_API_VERIFY` | Centrala task dispatch and verification endpoint | HTTPS POST (JSON payload) |
| `$AIDEVS_S04E04_NOTES_URL` | Zip archive containing Natan's notes (`ogloszenia.txt`, `rozmowy.txt`, `transakcje.txt`, `README.md`) | HTTPS GET / unzip |
| `$AIDEVS_S04E04_FILESYSTEM_PREVIEW_URL` | Visual HTML preview of the created virtual filesystem | Browser / HTTP GET |

---

## API Integration Schemas

### 1. Help Request & Response
- **Request:**
  ```json
  {
    "apikey": "...",
    "task": "filesystem",
    "answer": {
      "action": "help"
    }
  }
  ```
- **Expected Response:** Object containing command syntax, available filesystem actions, parameter definitions, and status codes.

### 2. Reset Request
- **Request:**
  ```json
  {
    "apikey": "...",
    "task": "filesystem",
    "answer": {
      "action": "reset"
    }
  }
  ```

### 3. File Creation Request (Single & Batch)
- **Single Action:**
  ```json
  {
    "apikey": "...",
    "task": "filesystem",
    "answer": {
      "action": "createFile",
      "path": "/miasta/opalino",
      "content": "{\"chleb\": 45, \"woda\": 120, \"mlotek\": 6}"
    }
  }
  ```
- **Batch Action:**
  ```json
  {
    "apikey": "...",
    "task": "filesystem",
    "answer": [
      {
        "action": "createFile",
        "path": "/miasta/opalino",
        "content": "{\"chleb\": 45, \"woda\": 120, \"mlotek\": 6}"
      },
      {
        "action": "createFile",
        "path": "/osoby/Iga_Kapecka",
        "content": "Iga Kapecka [Opalino](/miasta/opalino)"
      },
      {
        "action": "createFile",
        "path": "/towary/makaron",
        "content": "[Opalino](/miasta/opalino)"
      }
    ]
  }
  ```

### 4. Completion & Verification Request (`action: "done"`)
- **Request:**
  ```json
  {
    "apikey": "...",
    "task": "filesystem",
    "answer": {
      "action": "done"
    }
  }
  ```
- **Expected Response:** Success status containing `{FLG:...}` or validation feedback detailing errors in structure.

---

## Environment & Configuration Setup

The microservice requires the following environment variables configured in `.env` (local) and GCP Secret Manager (production):

```dotenv
# Centrala Authentication & Verification
AIDEVS_API_KEY="your-centrala-api-key"
AIDEVS_API_VERIFY="https://centrala.ag3nts.org/verify"

# Lesson-Specific Data Sources
AIDEVS_S04E04_NOTES_URL="https://hub.ag3nts.org/dane/natan_notes.zip"
AIDEVS_S04E04_FILESYSTEM_PREVIEW_URL="https://hub.ag3nts.org/filesystem_preview.html"

# Google Cloud Platform & Vertex AI
GOOGLE_CLOUD_PROJECT="af-aidevs"
GOOGLE_CLOUD_LOCATION="global"
GEMINI_MODEL="gemini-3.8-flash"
THINKING_LEVEL="low"

# BigQuery Telemetry
BIGQUERY_DATASET="s04e04"
BIGQUERY_TABLE_AUDIT="audit"

# Observability
LANGSMITH_TRACING="true"
LANGSMITH_API_KEY="your-langsmith-key"
LANGSMITH_PROJECT="af-aidevs"
```

---

## Acceptance & Verification Criteria

1. **Filesystem Structure Parity:**
   - Exactly three directories created: `/miasta`, `/osoby`, `/towary`.
   - All 8 cities from `ogloszenia.txt` exist under `/miasta/` with valid ASCII JSON containing integer quantities without units.
   - All 8 trade representatives from `rozmowy.txt` exist under `/osoby/<Firstname_Lastname>` with their full name and markdown link to their city.
   - All unique commodities from `transakcje.txt` exist under `/towary/<commodity>` in singular nominative ASCII form, each containing markdown link(s) to offering city/cities.
2. **Quality Gate Compliance:**
   - 100% test pass in `pytest` for parsing logic, normalization, and API clients.
   - Zero lint errors via `ruff check` and `ruff format`.
   - Static type checking clean via `mypy`.
   - Both **LangChain** and **Google ADK** execution backends fully supported with feature parity.
3. **Verification Flag Capture:**
   - Dispatching `done` successfully yields `{FLG:...}`.
   - Telemetry audit recorded in BigQuery table `af-aidevs.s04e04.audit`.
