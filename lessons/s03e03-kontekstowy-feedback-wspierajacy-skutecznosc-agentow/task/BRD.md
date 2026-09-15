# Business Requirements Document (BRD) — S03E03: Reactor Navigation (`reactor`)

## 1. Overview
Following the successful deployment and testing of the emergency cooling system software (from S03E02), the physical cooling controller module must be installed near the core of the power plant reactor. Due to extreme radiation levels, human entry is strictly prohibited. 

A remote transport robot must be programmed to navigate autonomously across a 7x5 reactor floor grid, carry the cooling module to its target mounting slot at the opposite end of the chamber, and avoid being crushed by moving reactor core blocks that cycle vertically in real time with each issued command.

---

## 2. Requirements

### 2.1 Functional Requirements
1. **Turn-Based Navigation Control**:
   - Issue sequential navigation commands to the robot via the verification API endpoint (`$AIDEVS_API_VERIFY`).
   - Valid commands:
     - `start`: Initiates the session and retrieves the initial board configuration.
     - `reset`: Restores the robot and reactor blocks to the initial state in case of collision or dead end.
     - `right`: Moves the robot 1 grid cell to the right along the floor (row 5).
     - `left`: Moves the robot 1 grid cell to the left along the floor (row 5).
     - `wait`: Advances the simulation by 1 step while the robot remains in its current grid position.
   - Strictly one command may be submitted per HTTP request.

2. **Reactor Floor & Grid Dynamics**:
   - The chamber floor grid consists of **7 columns** by **5 rows**.
   - Coordinate reference:
     - Starting Position (`P`): Column 1, Row 5 (bottom-left corner).
     - Target Goal (`G`): Column 7, Row 5 (bottom-right slot).
     - Empty Space (`.`): Traversible corridor cell.
     - Reactor Core Blocks (`B`): Vertical moving obstacles.
   - The robot strictly traverses along the bottom floor tier (Row 5).

3. **Obstacle Dynamics (Reactor Core Blocks)**:
   - Each reactor core block occupies exactly **2 vertical cells** (height = 2).
   - Blocks oscillate continuously in a vertical cycle:
     - Moving downwards until reaching the bottom boundary (covering rows 4 and 5).
     - Upon reaching the bottom limit, reversing direction upwards towards row 1.
     - Upon reaching the top limit (rows 1 and 2), reversing direction downwards.
   - Movement is deterministic and discrete: blocks advance by exactly 1 cell per issued robot command (including `wait`). Elapsed wall-clock time does not advance the state.

4. **Collision Avoidance & Survival**:
   - The robot must never occupy a cell that is currently occupied or entered by a reactor block (`B`).
   - If a collision occurs, the robot is destroyed, and the simulation must be reset.

5. **Decision & Pathfinding Logic**:
   - The autonomous controller must parse the board state and block velocity/direction vectors from each step's API response.
   - Heuristic / lookahead strategy:
     - Evaluate forward motion (`right`) if the destination column's floor cell will be clear of blocks at step `t+1`.
     - If advancing is unsafe (block descending or already blocking column `x+1`), evaluate holding position (`wait`).
     - If staying in place is unsafe (block in current column descending towards row 5), evaluate retreating (`left`).
   - The sequence concludes successfully when the robot enters Column 7, Row 5 (`G`), yielding the course completion flag (`{FLG:...}`).

---

## 3. System & Operational Constraints

### 3.1 Step Budget & Reliability
- Avoid excessive `reset` loops or trial-and-error thrashing. The solution must aim for a deterministic, zero-collision traversal on the first attempt using state projection.
- Maximize execution efficiency while respecting API latency.

### 3.2 Context & Model Reasoning
- Turn-based simulation updates provide immediate feedback.
- The agent or algorithm must reliably track:
  - Current robot column `x \in [1, 7]`.
  - Positions and direction vectors of all active column blocks.
  - History of executed moves.

---

## 4. Data Inputs & Environment Setup

### 4.1 Environment Variables
All sensitive credentials and external endpoints must be stored exclusively in `.env`:

| Variable Name | Description | Example / Fallback |
|---|---|---|
| `AIDEVS_API_KEY` | Personal course API authorization key | `[SECRET]` |
| `AIDEVS_API_VERIFY` | Central verification and command execution API endpoint | Configured in `.env` |
| `AIDEVS_REACTOR_PREVIEW_URL` | Optional visual dashboard URL for monitoring reactor state | Configured in `.env` |

*(Note: Raw URLs must never be hardcoded in repository code or documentation).*

---

## 5. API Integration

### 5.1 Command Dispatch & Verification (`$AIDEVS_API_VERIFY`)
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`
- **Request Payload**:
  ```json
  {
    "apikey": "$AIDEVS_API_KEY",
    "task": "reactor",
    "answer": {
      "command": "start"
    }
  }
  ```
- **Valid Command Values**: `"start"`, `"reset"`, `"right"`, `"left"`, `"wait"`.
- **Response Structure**:
  - HTTP 200 with JSON payload containing:
    - Current board map representation (ASCII grid or string array).
    - Status message / feedback.
    - Reactor block positions and direction indicators (up / down).
    - Course flag `{FLG:...}` upon successfully reaching goal cell `G`.

---

## 6. Success Criteria
1. Initial command `start` sent and valid initial grid state received.
2. Traversal algorithm accurately projects block kinematics and avoids all collisions.
3. Robot reaches destination cell (Column 7, Row 5) without suffering structural damage.
4. Final API response confirms module installation and returns the course flag `{FLG:...}`.
