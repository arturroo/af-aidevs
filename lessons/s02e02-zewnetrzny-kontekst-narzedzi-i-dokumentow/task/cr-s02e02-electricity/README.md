# S02E02: Autonomous Electrical Circuit Solver (`cr-s02e02-electricity`)

## 1. Overview & Objective
This service autonomously solves the 3x3 electrical grid circuit puzzle from AI_Devs S02E02 to route electrical power from the emergency source at tile `3x1` to the three power plant units (`PWR6132PL`, `PWR1593PL`, `PWR7264PL`).

The workflow is orchestrated using **LangChain 1.2.15** / **Google ADK** and interacts strictly through:
1. **`cr-mcp-web-gateway`**: External network isolation for file downloads (`fetch_web_resource`) and REST verification dispatches (`post_web_resource`).
2. **`cr-mcp-workspace` & GCS FUSE (`/mnt/workspaces`)**: Session-isolated file storage for storing downloaded board images and writing execution summaries (`run_notes.txt`).
3. **Real-Time BigQuery Auditing (`af-aidevs.s02e02.audit`)**: Zero-latency async callback streaming for full traceability.

---

## 2. Architecture & Execution Flow

```mermaid
sequenceDiagram
    autonumber
    participant Agent as LangChain Agent (Cloud Run)
    participant WebGW as MCP Web Gateway
    participant GCS as Cloud Storage (/mnt/workspaces)
    participant Hub as External Hub API (hub.ag3nts.org)
    participant BQ as BigQuery Audit

    Agent->>WebGW: fetch_web_resource(url=".../electricity.png?reset=1", output_path="electricity.png")
    WebGW->>Hub: GET .../electricity.png?reset=1
    Hub-->>WebGW: Reset board image binary
    WebGW->>GCS: Write electricity.png to session workspace
    
    Agent->>Agent: inspect_circuit_grid(image_path="electricity.png")
    Note over Agent: Reads /mnt/workspaces/.../electricity.png<br/>Extracts tile pinouts & computes CW rotation delta
    
    loop For each of the 5 required tile rotations
        Agent->>WebGW: post_web_resource(url="/verify", payload={"rotate": "AxB"})
        WebGW->>Hub: POST /verify
        Hub-->>WebGW: {"code": 1|0, "message": "Done" | "{FLG:...}"}
    end
    
    Agent->>GCS: write_file(file_path="run_notes.txt", content="Report with [REDACTED_FLAG]")
    Agent->>BQ: Stream session_end audit event
```

---

## 3. Key Calibration & Engineering Discoveries

### 3.1 Live Grid Slicing Geometry
The live board served from `https://hub.ag3nts.org/data/{API_KEY}/electricity.png` is **800x450 px**, while the solved schematic is **598x422 px**.
* **Precise $800 \times 450$ coordinates**: $(X_0=238, Y_0=100, \text{tile\_w}=95, \text{tile\_h}=95)$.
* **Safe Margin Edge Sampling**: Sampling margins must be centered away from tile borders (`arr[10:25, 40:55]` for top, `arr[70:85, 40:55]` for bottom, `arr[40:55, 10:25]` for left, `arr[40:55, 70:85]` for right) to prevent outer grid divider lines from bleeding into tile pinouts.

### 3.2 Ground Truth Solution (5 Operations)
From a clean reset state (`?reset=1`), the true circuit requires exactly 5 sequential 90-degree CW operations:
1. `1x2`: 1 rotation
2. `1x3`: 1 rotation
3. `2x1`: 1 rotation
4. `2x2`: 3 rotations
5. `3x1`: 1 rotation

Upon the 5th rotation, the verification server returns `{"code": 0, "message": "{FLG:...}"}`.

---

## 4. Lessons Learned & Future Refactoring (A2A Vision Subagent)

### 4.1 Pragmatic Decision Context
* **Decision**: We consolidated the vision analysis into a hermetic function-calling tool (`inspect_circuit_grid`) inside `cr-s02e02-electricity` reading directly from the mounted GCS workspace (`/mnt/workspaces`), rather than deploying a separate `cr-agent-vision` microservice.
* **Rationale**: Strict timeline constraint to complete **Season 2, Season 3, and Season 4 by the end of September 2026**. Shipping a working, fully auditable, and secure implementation was prioritized over building an extra standalone microservice for this single task.

### 4.2 Security & Blast Radius Tradeoff
* **Current Setup**: `sa-cr-s02e02-electricity` holds `roles/storage.objectViewer` on `af-aidevs-workspaces` with `/mnt/workspaces` mounted as a read-only GCS FUSE volume.
* **Target Zero-Trust Pattern**:
  1. The orchestrator agent should have **zero direct storage permissions**.
  2. A dedicated `cr-agent-vision` microservice runs in the internal perimeter and accepts image references (or scoped 2-minute signed URLs).
  3. The vision specialist parses the schematic and returns structured `TilePinout` / `GridCircuitSolverData` responses over authenticated A2A (Agent-to-Agent) endpoints.

### 4.3 Blueprint to Resume A2A Migration
When revisiting this lesson:
1. Create `cloud_run/cr-agent-vision` microservice exposing `POST /inspect` conforming to `af_aidevs.schemas.vision.GridCircuitSolverData`.
2. Update Terraform `cr_names` to provision `cr-agent-vision` with GCS read permissions and grant `sa-cr-s02e02-electricity` `roles/run.invoker` on `cr-agent-vision`.
3. Swap `inspect_circuit_grid` tool implementation to invoke the remote `cr-agent-vision` endpoint via OIDC-authenticated HTTP client.
