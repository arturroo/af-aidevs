# Business Requirements Document (BRD) - S05E05: Pocket Time Machine Operation & Temporal Trajectory Navigation (timetravel)

## 1. Overview & Business Objectives

In the dramatic conclusion of the resistance timeline, Operative Number Five stands inside the cave complex in Grudziądz equipped with the portable time machine **CHRONOS-P1** (manufactured by ACME in May 2231). The ultimate mission objective is to open a permanent temporal tunnel to **November 12, 2024** — precisely one day before resistance leader Rafał was discovered unconscious inside the cave.

However, the pocket device's battery packs (`XLPWR-A`) do not possess sufficient charge to open a high-energy temporal tunnel directly from the current baseline. The temporal navigation plan requires an intermediate, multi-hop itinerary:
1. **Jump 1 (Future Transit):** Perform a discrete temporal jump to **November 5, 2238** (`2238-11-05`), where a resistance operative will deliver a fresh pack of high-capacity batteries.
2. **Jump 2 (Return Transit):** Swap the depleted batteries for the fresh cells and return to the device's present baseline date ("Teraźniejszość").
3. **Jump 3 (Temporal Tunnel Creation):** With battery capacity fully replenished (>= 60%), configure and lock open a stabilized, bidirectional **Time Tunnel** to **November 12, 2024** (`2024-11-12`), rendezvous with Rafał, and retrieve the final operational flag (`{FLG:...}`).

Navigating the CHRONOS-P1 requires a **hybrid operational architecture**:
- Certain temporal parameters (`year`, `month`, `day`, `syncRatio`, `stabilization`) are configured via programmatic REST API (`$AIDEVS_API_VERIFY`).
- Other physical parameters (`PT-A`, `PT-B`, `PWR` shield protection, `standby`/`active` operational mode, and trigger detonation) are controlled via the hardware cockpit web preview interface (`$AIDEVS_TIMETRAVEL_PREVIEW_URL`).
- Core hardware state (`internalMode`, `fluxDensity`, `batteryLevel`, device integrity) evolves autonomously based on internal core oscillation cycles.

The business objective of the `timetravel` task is to engineer an intelligent Temporal Flight Director (interactive CLI assistant and/or dual-agent orchestrator) that interprets technical device documentation, computes exact temporal mechanics, orchestrates API configurations, monitors real-time telemetry, and guides cockpit operations to safely traverse time without terminal radiation poisoning or paradox collapse.

---

## 2. Chronodynamics & Temporal Mechanics

The operation of the CHRONOS-P1 pocket time machine is governed by the official ACME hardware specification. Every parameter must satisfy strict physical tolerances before core ignition (`Flux Density = 100%`) is granted.

### 2.1 Multi-Hop Mission Trajectory

| Phase | Operation Type | Target Date | Direction Switches | Internal Mode | Target Shield PWR | Mission Milestone |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Phase 1** | Time Jump (`Skok`) | `2238-11-05` | `PT-A = OFF`, `PT-B = ON` | Mode 3 ($2151 \le Y \le 2300$) | `PWR = 91` | Retrieve fresh battery pack |
| **Phase 2** | Time Jump (`Skok`) | Device Baseline Present Date | `PT-A = ON`, `PT-B = OFF` | Mode matching present year | PWR matching present year | Return with fresh power cells |
| **Phase 3** | Time Tunnel (`Tunel`) | `2024-11-12` | `PT-A = ON`, `PT-B = ON` | Mode 2 ($2000 \le Y \le 2150$) | `PWR = 19` | Establish tunnel to Rafał; capture flag |

---

### 2.2 Mathematical Specifications

#### Temporal Synchronization Ratio (`syncRatio`)
Every temporal jump or tunnel requires computing a discrete synchronization ratio based on the target date components:
- Fixed weights:
  - $\text{Day weight } W_d = 8$
  - $\text{Month weight } W_m = 12$
  - $\text{Year weight } W_y = 7$
- Arithmetic formula:
  $$\text{SyncRaw} = (D \times 8 + M \times 12 + Y \times 7) \pmod{101}$$
- API Representation:
  - Formatted as a decimal number between `0.00` and `1.00` with 2 decimal places:
    $$\text{syncRatio} = \frac{\text{SyncRaw}}{100.0} \quad (\text{e.g. } 82 \to 0.82, \; 54 \to 0.54, \; 100 \to 1.00)$$

*Precomputed Verification Checkpoints:*
- For `2238-11-05`:
  $$\text{SyncRaw} = (5 \times 8 + 11 \times 12 + 2238 \times 7) \pmod{101} = (40 + 132 + 15666) \pmod{101} = 15838 \pmod{101} = 82 \implies \mathbf{0.82}$$
- For `2024-11-12`:
  $$\text{SyncRaw} = (12 \times 8 + 11 \times 12 + 2024 \times 7) \pmod{101} = (96 + 132 + 14168) \pmod{101} = 14396 \pmod{101} = 54 \implies \mathbf{0.54}$$

#### Hardware Operating Phase (`internalMode`)
The internal core cycles autonomously across four discrete operational modes every few seconds. An ignition attempt during an incompatible phase causes emergency core shutdown:
- **Mode 1:** Covers target years $Y < 2000$.
- **Mode 2:** Covers target years $2000 \le Y \le 2150$ *(applicable to target year 2024)*.
- **Mode 3:** Covers target years $2151 \le Y \le 2300$ *(applicable to target year 2238)*.
- **Mode 4:** Covers target years $Y \ge 2301$.

#### Environmental Radiation Shielding (`PWR`)
The CHRONOS-P1 deploys a 500-meter safety envelope against radiation, fallout, and toxic particulates. The shield potentiometer (`PWR`, range $0 - 100$) must precisely match the environmental toxicity index for the target year recorded in the ACME documentation:
- Year **2238**: $\mathbf{PWR = 91}$
- Year **2024**: $\mathbf{PWR = 19}$
- Present Year: Look up from the local documentation lookup table (`timetravel.md`).

#### Direction Switches (`PT-A` & `PT-B`)
- **Past Transit (`PT-A`):** Engaged when navigating backwards in the timeline.
- **Future Transit (`PT-B`):** Engaged when navigating forwards in the timeline.
- **Time Tunnel (`PT-A` AND `PT-B`):** Both switches engaged simultaneously. Establishes a continuous bidirectional corridor between the baseline present and destination date. Requires battery capacity $\ge 60\%$.

#### Flux Density (`fluxDensity`)
- Dynamic core readiness metric ($0\% - 100\%$).
- Reaches $\mathbf{100\%}$ only when all temporal coordinates (`day`, `month`, `year`), `syncRatio`, `stabilization`, `PWR`, switches (`PT-A`, `PT-B`), and operational state (`active`) are aligned.
- Ignition sphere pulses green and unlocks detonation only at $\mathbf{100\%}$.

---

## 3. Hybrid Operational Architecture

The division of responsibility between the software API and the hardware cockpit is strictly defined:

```
+-----------------------------------------------------------------------------------+
|                            OPERATIONAL CONTROL MATRIX                             |
+------------------------------------------+----------------------------------------+
|   Programmatic REST API ($AIDEVS_API_VERIFY) |  Cockpit Hardware GUI ($AIDEVS_TIMETRAVEL_PREVIEW) |
+------------------------------------------+----------------------------------------+
| 1. Target Year (`year`)                   | 1. Direction Past Switch (`PT-A`)      |
| 2. Target Month (`month`)                 | 2. Direction Future Switch (`PT-B`)    |
| 3. Target Day (`day`)                     | 3. Radiation Shield Potentiometer (`PWR`)|
| 4. Temporal Sync Ratio (`syncRatio`)     | 4. System Operating State (standby/active)|
| 5. Core Stabilization (`stabilization`)  | 5. Ignition Sphere Detonator Trigger   |
| 6. Telemetry & State Polling (`getConfig`)|                                        |
| 7. Emergency Core Reset (`reset`)        |                                        |
+------------------------------------------+----------------------------------------+
```

### Critical Operational Constraints
1. **Standby Lock:** API configuration commands (`action: "configure"`) are accepted **strictly when the device is in `standby` mode**. Modifying parameters during `active` mode triggers a hardware lockout error.
2. **Dynamic Stabilization Hints:** The `stabilization` parameter cannot be precomputed purely offline; upon configuring the target date via API, the central system generates dynamic temporal distortion hints accessible via API responses or `getConfig`. The assistant must inspect these hints and inject the matching stabilization value.
3. **InternalMode Synchronization:** Operators cannot force `internalMode`. The software assistant must continuously poll or monitor `internalMode` and alert the operator the exact instant the matching mode becomes active.
4. **Energy Management:** Discrete jumps consume $\approx 33\%$ battery. Time tunnels consume significantly more power and require $\ge 60\%$ initial charge. Draining battery to $0\%$ locks the unit into emergency recovery (`reset` only).

---

## 4. API Integration & Protocol Specifications

### 4.1 Verification Endpoint
All programmatic interactions dispatch JSON payloads to the central verification gateway:
- **Target URL:** `$AIDEVS_API_VERIFY`
- **Method:** `POST`
- **Headers:** `Content-Type: application/json`

### 4.2 Request Envelope
```json
{
  "apikey": "$AIDEVS_API_KEY",
  "task": "timetravel",
  "answer": {
    "action": "<action_name>",
    ...
  }
}
```

### 4.3 Supported API Actions

#### 1. System Help (`help`)
Retrieves API syntax and allowable command parameters:
```json
{
  "apikey": "$AIDEVS_API_KEY",
  "task": "timetravel",
  "answer": {
    "action": "help"
  }
}
```

#### 2. Telemetry Interrogation (`getConfig`)
Polls current hardware configuration, active date registers, stabilization hints, battery level, and temporal state:
```json
{
  "apikey": "$AIDEVS_API_KEY",
  "task": "timetravel",
  "answer": {
    "action": "getConfig"
  }
}
```

#### 3. Parameter Configuration (`configure`)
Configures a discrete temporal register while the machine is in `standby`:
```json
{
  "apikey": "$AIDEVS_API_KEY",
  "task": "timetravel",
  "answer": {
    "action": "configure",
    "param": "<param_name>",
    "value": "<param_value>"
  }
}
```
*Allowable Parameters:*
- `year` (integer: $1500 - 2499$)
- `month` (integer: $1 - 12$)
- `day` (integer: $1 - 31$)
- `syncRatio` (float / 2 decimal places: `0.00` - `1.00`)
- `stabilization` (value dynamically determined from API advice / hints)

#### 4. Emergency Core Reset (`reset`)
Restores initial factory baseline registers if battery is depleted or configuration is corrupted:
```json
{
  "apikey": "$AIDEVS_API_KEY",
  "task": "timetravel",
  "answer": {
    "action": "reset"
  }
}
```

---

## 5. System Requirements & Functional Scope

### 5.1 Flight Director Capabilities (Core Service & CLI)
1. **Documentation Knowledge Base:** Embed or parse the local `timetravel.md` lookup table to instantly resolve `PWR` values for any year between 1500 and 2499 without external network requests.
2. **Deterministic Temporal Math Engine:** Compute exact `syncRatio` with decimal formatting according to the modular weight formula.
3. **Automated API Choreography:**
   - Execute baseline interrogation (`getConfig`) to record initial present date.
   - Inject coordinates (`year`, `month`, `day`, `syncRatio`) sequentially.
   - Ingest API stabilization hints and apply required `stabilization` adjustments.
4. **Real-Time Operator Guidance System:**
   - Display clear, structured terminal instructions indicating exactly what cockpit switches (`PT-A`, `PT-B`, `PWR`) need to be adjusted.
   - Monitor `internalMode` in real time, alerting the operator with a countdown or immediate trigger notification when `internalMode` matches the destination epoch.
   - Detect `Flux Density = 100%` and signal the green light for sphere activation.
5. **Phase Progression Orchestrator:**
   - Guide Jump 1 (2238 battery retrieval).
   - Verify battery replenishment.
   - Guide Jump 2 (Return to present baseline).
   - Guide Jump 3 (Tunnel creation to 2024-11-12).
   - Capture, log, and display the final Central verification flag.

### 5.2 Dual-Agent / Autonomous Option ("Wersja dla ambitnych")
In addition to the Human-in-the-Loop CLI Flight Director, the system architecture can support an automated Cockpit Browser Agent (using Playwright or CDP) that interacts with `$AIDEVS_TIMETRAVEL_PREVIEW_URL`, synchronizing with the Backend Director Agent via a shared state file or IPC to achieve 100% autonomous hands-free temporal navigation.

---

## 6. Security, Environment & Privacy Guardrails

1. **Zero Hardcoded URLs:**
   - `$AIDEVS_API_VERIFY`: Canonical endpoint for Central API verification.
   - `$AIDEVS_TIMETRAVEL_PREVIEW_URL`: Web cockpit GUI URL.
   - `$AIDEVS_TIMETRAVEL_DOCS_URL`: ACME documentation URL.
   - Under no circumstances may raw domain URLs appear in committed code, public markdown, or telemetry.
2. **Secret Management:**
   - `AIDEVS_API_KEY` stored exclusively in GCP Secret Manager (production) and local `.env` (development).
3. **Flag Protection:**
   - Any captured course flag (`{FLG:...}`) must be strictly redacted in public commits, PRDs, and documentation.
4. **Local Repository Hygiene:**
   - The ACME technical manual `timetravel.md` is strictly gitignored (`**/lessons/*/timetravel.md`) alongside lesson markdown files.

---

## 7. Acceptance & Verification Criteria

- [ ] **Temporal Math Verification:** Unit tests validate `syncRatio` for known fixtures (`2238-11-05` $\to 0.82$, `2024-11-12` $\to 0.54$, boundary modulo cases).
- [ ] **PWR Table Accuracy:** Table lookup matches ACME documentation for key years ($2238 \to 91$, $2024 \to 19$, present year).
- [ ] **API Client Compliance:** Successfully dispatches `help`, `getConfig`, `configure`, and `reset` payloads conforming to the Central API schema.
- [ ] **State Machine Integrity:** Accurately detects `standby` vs `active` restrictions, preventing API configuration calls while active.
- [ ] **Multi-Hop Trajectory Execution:**
  - [ ] Jump 1 to `2238-11-05` executed with `PWR=91`, `PT-B=ON`, `internalMode=3`.
  - [ ] Battery replenishment confirmed.
  - [ ] Jump 2 return to baseline present executed.
  - [ ] Jump 3 tunnel to `2024-11-12` executed with `PWR=19`, `PT-A=ON`, `PT-B=ON`, `internalMode=2`.
- [ ] **Final Deliverable:** Official mission flag captured and recorded.
