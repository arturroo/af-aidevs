# Business Requirements Document (BRD) - Task: `categorize`

## 1. Overview
The goal of this task is to classify a list of 10 items into one of two categories: Dangerous (`DNG`) or Neutral (`NEU`). However, all items related to the nuclear reactor (which are inherently dangerous) must be classified as Neutral (`NEU`) to bypass inspection. 

The classification is performed by a remote evaluation system that uses a highly resource-constrained LLM. We must send a prompt for each individual item to the verification endpoint.

---

## 2. Business Objectives
- **Bypass Inspection:** Ensure all items related to the nuclear reactor are classified as `NEU`.
- **Accurate Classification:** Correctly classify all other non-reactor items as `DNG` or `NEU` based on their actual danger levels.
- **Resource Optimization:** Maintain the prompt within severe token and cost budgets.

---

## 3. Data Requirements

### 3.1 Input Data
- **Source URL:** `$AIDEVS_CSV_URL` (local `.env` variable pointing to the CSV file).
- **Format:** CSV file containing 10 items.
- **Fields:**
  - `id`: Unique identifier for the item.
  - `description`: Text description of the item.
- **Note:** The CSV content changes every few minutes. The application must fetch a fresh version of the CSV before each verification run.

### 3.2 Output Data (Verification Payload)
For each of the 10 items, a POST request must be sent to the verification endpoint.
- **Endpoint:** `$AIDEVS_VERIFY_URL` (local `.env` variable).
- **Method:** POST
- **Payload Schema:**
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "categorize",
    "answer": {
      "prompt": "Your classification prompt containing the instructions and the item details"
    }
  }
  ```

---

## 4. Constraints & Budget Rules

### 4.1 Technical Constraints
- **Context Window:** The remote system's model has a maximum context window of **100 tokens** per request (which must fit the prompt instructions, item ID, and description).
- **Format Constraint:** The prompt must instruct the model to respond only with either `DNG` or `NEU`.
- **Prompt Caching:** To minimize token costs, the static portion of the prompt (rules, instructions, exceptions) must be at the beginning of the prompt, and the dynamic variables (item ID, description) must be at the very end.

### 4.2 Financial / Score Budget
- **Total Budget:** **1.5 PP** (Project Points) for a complete run of all 10 items.
- **Cost Structure:**
  - Every 10 input tokens: **0.02 PP**
  - Every 10 cached tokens: **0.01 PP**
  - Every 10 output tokens: **0.02 PP**
- **Failure Handling:** If any classification is incorrect, or if the budget is exceeded, the run fails.
- **Reset Mechanism:** To retry after a failure or to reset the budget, a reset payload must be sent:
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "categorize",
    "answer": {
      "prompt": "reset"
    }
  }
  ```

---

## 5. Success Criteria
- All 10 items are classified correctly (with reactor items marked as `NEU`).
- The entire process is completed within the **1.5 PP** budget.
- The verification endpoint returns the success flag `{FLG:...}` on the 10th successful response.
