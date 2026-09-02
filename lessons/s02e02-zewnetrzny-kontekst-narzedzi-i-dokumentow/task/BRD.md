# Business Requirements Document (BRD) - Task: `electricity`

## 1. Overview
The goal of this task is to solve an electrical routing puzzle on a 3x3 grid by rotating grid tiles so that electric power from an emergency power source (located at the bottom-left corner `3x1`) is correctly routed to all three power plant units: `PWR6132PL`, `PWR1593PL`, and `PWR7264PL`. The resulting electrical wiring must form a valid closed circuit matching the target configuration schema.

The system interacts with the remote course platform API to fetch the current board state (rendered as a PNG image), determine required rotations, submit individual rotation commands, and receive the completion flag (`{FLG:...}`).

---

## 2. Business Objectives
- **Restore Nuclear Plant Power:** Successfully connect the emergency power feed to all 3 nuclear power plant units (`PWR6132PL`, `PWR1593PL`, `PWR7264PL`).
- **Closed Circuit Alignment:** Ensure all cable segments align strictly with the target solution diagram.
- **Efficient Rotation Operations:** Accurately detect the current tile orientations and compute the minimal number of 90° clockwise rotations needed to minimize API calls.
- **Automated Verification & Flag Retrieval:** Submit rotation commands sequentially and capture the final flag `{FLG:...}`.

---

## 3. Data & API Requirements

### 3.1 Input Data
- **Current Board State:**
  - **Source URL:** `$AIDEVS_ELECTRICITY_DATA_URL` (dynamic PNG image representing the 3x3 grid state).
  - **Format:** PNG image.
  - **Grid Addressing:** Tiles are addressed as `AxB`, where `A` is the row (1-3, top to bottom) and `B` is the column (1-3, left to right):
    ```
    1x1 | 1x2 | 1x3
    ----|-----|----
    2x1 | 2x2 | 2x3
    ----|-----|----
    3x1 | 3x2 | 3x3
    ```
- **Target Solved Schema:**
  - **Source URL:** `$AIDEVS_ELECTRICITY_SOLVED_URL` (static PNG image showing the target solved circuit state).
  - **Format:** PNG image.

### 3.2 Rotation & Verification API
Each rotation requires a separate POST request to the central verification endpoint.
- **Endpoint:** `$AIDEVS_VERIFY_URL`
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`
- **Payload Schema:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "electricity",
    "answer": {
      "rotate": "2x3"
    }
  }
  ```
- **Mechanics:**
  - Each call to the endpoint with `"rotate": "AxB"` rotates tile `AxB` by **90 degrees clockwise**.
  - Multiple rotations on the same or different tiles require individual sequential POST requests.
  - Upon submitting the final correct rotation, the API response body contains the completion flag `{FLG:...}`.

### 3.3 Board Reset API
If the puzzle reaches an invalid or desynchronized state, the board can be reset to its initial layout.
- **Endpoint:** `$AIDEVS_ELECTRICITY_RESET_URL` (or GET `$AIDEVS_ELECTRICITY_DATA_URL?reset=1`)
- **Method:** `GET`

---

## 4. Constraints & Rules

### 4.1 Grid & Electrical Constraints
- **Grid Size:** Fixed 3x3 matrix (9 tiles in total).
- **Source Tile:** Located at row 3, column 1 (`3x1`, bottom-left corner).
- **Power Plants:** `PWR6132PL`, `PWR1593PL`, `PWR7264PL`.
- **Circuit Integrity:** The circuit must be closed and match the reference design exactly.

### 4.2 API & Execution Constraints
- **Single Rotation per Call:** One HTTP POST request per 90° clockwise rotation.
- **Rotation Calculation:** To rotate 90° counter-clockwise (CCW), execute 3 clockwise (CW) rotations.
- **Vision Model Latency & Token Efficiency:** State interpretation can be performed by a multimodal vision model (e.g. `gemini-3.5-flash`) by segmenting the grid into tiles or analyzing the full board vs. reference.

---

## 5. Environment Setup & Security Requirements
All endpoints and secrets must be loaded strictly from local `.env` files or GCP Secret Manager and never hardcoded in source code or documentation:

| Environment Variable | Description |
|---|---|
| `AIDEVS_API_KEY` | User API authentication key for the AI_Devs platform |
| `AIDEVS_VERIFY_URL` | Central verification endpoint URL |
| `AIDEVS_ELECTRICITY_DATA_URL` | Endpoint to fetch the current board state PNG image |
| `AIDEVS_ELECTRICITY_SOLVED_URL` | Endpoint to fetch the reference solved board PNG image |
| `AIDEVS_ELECTRICITY_RESET_URL` | Endpoint to reset the electricity puzzle board state |

---

## 6. Success Criteria
1. Current puzzle state and target reference schema are correctly retrieved and parsed.
2. The exact rotation delta for each tile (`0`, `1`, `2`, or `3` steps CW) is calculated.
3. Rotation requests are sent to `$AIDEVS_VERIFY_URL` until all tiles match the reference circuit.
4. Final API response is verified, and the flag in format `{FLG:...}` is captured and logged.
