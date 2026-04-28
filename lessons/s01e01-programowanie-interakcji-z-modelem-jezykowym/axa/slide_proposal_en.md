# Slide: Code or AI? Architecture Selection Strategy

## Header: Determinism vs. Probabilism (Foundation S01E01)

| Criterion | Traditional Code (Determinism) | AI Model / Agent (Probabilism) |
| :--- | :--- | :--- |
| **Main Goal** | Precise execution of instructions | Autonomous goal achievement (Goal-oriented) |
| **Principle** | **First Choice (Highest ROI).** If it can be done with code — do it with code. | **Last Resort.** Use only where code fails. |
| **Guarantee** | 100% repeatability (A -> B) | No guarantee. Requires risk management. |
| **Process Stability** | Fully defined and stable (e.g., invoices) | Dynamic, evolving, ambiguous (e.g., ChatBot) |
| **Precision** | Critical (Finance, Compliance, 100%) | Nuance, context, interpretation (e.g., PDF summaries) |
| **Latency** | Milliseconds (Real-time) | Seconds/Minutes (NRT - Near Real Time), dependent on response length and token generation speed |
| **Logic** | Linear (if-then-else) | Reasoning, planning, adaptation to unforeseen context and intent |
| **Application** | Algorithms, RegEx, SQL (e.g., fixed date formats) | Unstructured data, intent (calculating dates from context, e.g., "Let's meet next Friday") |
| **Cost** | Constant / Minimal (CPU, Memory) | High (we pay for every **token**) |
| **Errors** | Logical (Easy to debug) | Hallucinations, reasoning errors, Autoregression (no "undo" during token generation) |
| **Input Data** | Structured, clean | Unstructured, ambiguous |

---

### Golden rule from the lesson:
> "If you can draw the task's algorithm on a piece of paper — use code. Introduce AI only where flexibility and 'feeling' the context are necessary."

---

### Key principles from the lesson:
- **Autoregression:** The model cannot "undo" a generated token. An error at the beginning spoils the entire result.
- **Agent:** It's not just a chat, it's an LLM equipped with **tools** and capable of flexible interaction with the environment through these tools.

---

## Extension: When AI Workflow, and when AI Agent?
When traditional code is not enough, choose the right level of AI autonomy:

### Anthropic (Workflow vs. Agent)
- **AI Workflow:** Use when the process can be enclosed in fixed steps (rigid chain of prompts).
- **AI Agent:** Use only when the path to the goal is unknown and requires autonomous decision-making in a loop.
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) – Key article on moving from simple workflows to advanced agents.

---
**Developed by: Joi for Artur (2026-04-28)**
