# When to use traditional software, and when an AI program or AI agent?

## Determinism vs. Probabilism (Foundation S01E01)

| Criterion | Traditional Code (Determinism) | AI Model / Agent (Probabilism) |
| :--- | :--- | :--- |
| **Main Goal** | Precise execution of instructions | Autonomous judgment (within set boundaries) of next steps to achieve the defined goal |
| **Principle** | **First Choice (Highest ROI).** If it can be done with code — do it with code | **Last Resort.** Use only where code fails |
| **Guarantee** | 100% repeatability (A -> B) | No guarantee. Requires risk management |
| **Process Stability** | Fully defined and stable (e.g., invoices) | Dynamic, evolving, ambiguous (e.g., ChatBot) |
| **Precision** | Critical (Finance, Compliance, 100%) | Nuance, context, interpretation (e.g., PDF summaries) |
| **Latency** | Milliseconds (Real-time) | Seconds/Minutes (NRT - Near Real Time), dependent on response length and token generation speed |
| **Logic** | Linear (if-then-else) | Reasoning, planning, adaptation to unforeseen context and intent |
| **Application** | Algorithms, RegEx, SQL (e.g., fixed date formats) | Unstructured data, intent recognition (calculating dates from context, e.g., "Let's meet next Friday") |
| **Cost** | Constant / Minimal (CPU, Memory) | High (we pay for every **token**) |
| **Errors** | Logical (Easy to debug) | Hallucinations, reasoning errors, Autoregression (no "undo" during token generation — early error spoils the whole result) |
| **Input Data** | Structured, clean | Unstructured, ambiguous |

---

### Golden rule from the course:
> "If you can draw the task's algorithm on a paper — use code. Introduce AI only where flexibility and understanding of the context are necessary."

---

### Decision Flow:
1. **Is the process stable and described by hard rules?** ➔ **TRADITIONAL CODE**
2. **Are you predicting values or classifying with historical data?** ➔ **TRADITIONAL AI (ML)**
3. **Does the task require reasoning, interpretation, or fast go-to-market (GTM)?** ➔ **GENERATIVE AI (Workflow or Agent)**

---

### Extension: Workflow or Agent?
Once you choose AI, match the level of autonomy:
- **AI Workflow:** Use when the process can be enclosed in fixed steps (rigid chain of prompts).
- **AI Agent:** Use when the path to the goal is unknown and requires autonomous decision-making in a loop.

---
*Sources:*
- *Course: [AI_devs 4 Builders](https://aidevs.pl)*
- *Anthropic: [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)*
- *Google Cloud: [GenAI or Traditional AI](https://cloud.google.com/docs/ai-ml/generative-ai/generative-ai-or-traditional-ai)*
