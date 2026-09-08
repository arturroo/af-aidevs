# Gemini 3.8 Flash Developer Guide

## Overview

**Gemini 3.8 Flash** (`gemini-3.8-flash`) is Google's flagship "workhorse" model in the Flash series, released as Generally Available (GA) on **2026-09-02**. It is engineered specifically for autonomous agent workflows, long-horizon software engineering, multi-step orchestration, and iterative tool calling, delivering frontier-level intelligence while maintaining Flash-tier speed and cost efficiency.

Starting **2026-09-07** (from lesson `s02e04` onwards), `gemini-3.8-flash` is the default LLM across our Vertex AI agent architectures.

---

## Model Specifications

| Parameter | Specification |
| :--- | :--- |
| **Model ID** | `gemini-3.8-flash` |
| **Provider** | Google Cloud Vertex AI / Gemini Enterprise Agent Platform |
| **Context Window (Input)** | 1,048,576 tokens (~1M tokens) |
| **Max Output Tokens** | 65,536 tokens |
| **Modalities** | Text, Code, Images, Audio, Video, PDF |
| **Default Location** | `GOOGLE_CLOUD_LOCATION=global` (also available in `us-central1`, `europe-west6`, `europe-west1`) |
| **Supported Features** | Function calling / Tool use, Structured Outputs, Context Caching, Code Execution, Search Grounding |

---

## Pricing & Token Economics

Reference: [Google Cloud Agent Platform Pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing?hl=en)

Google provides an introductory promotional rate through the end of 2026:

### Token Rates

| Period | Input (per 1M tokens) | Output (per 1M tokens) |
| :--- | :--- | :--- |
| **Introductory (until 2026-12-31)** | **$0.75** | **$3.75** |
| **Standard (effective 2027-01-01)** | **$1.50** | **$7.50** |

### Context Caching Rates

| Period | Cache Write / Input (per 1M tokens) | Cache Storage (per 1M tokens / hour) |
| :--- | :--- | :--- |
| **Introductory (until 2026-12-31)** | $0.075 | $0.50 |
| **Standard (effective 2027-01-01)** | $0.150 | $1.00 |

> [!TIP]
> Context caching delivers up to 90% cost savings on long-context prompts, shared knowledge bases, and large static documents.

---

## Thinking & Reasoning Configuration

Gemini 3.8 Flash introduces native, iterative reasoning traces controlled by the `thinking_level` parameter. Rather than manual token budget guessing, developers can select from qualitative levels:

| Level | Latency Impact | Reasoning Depth | Recommended Use Cases |
| :--- | :--- | :--- | :--- |
| `LOW` | Minimal | Fast, concise reflection | Classification, simple extraction, single-turn lookups |
| `MEDIUM` *(Default)* | Moderate | Balanced step-by-step reasoning | Standard agent tool selection, contract validation |
| `HIGH` | Extended | In-depth planning & verification | Multi-hop code refactoring, complex puzzle solving, multi-agent arbitration |

### Configuration Example via `google-genai` SDK / ADK

```python
from google import genai
from google.genai import types

client = genai.Client(vertexai=True, project="af-aidevs", location="global")

response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents="Analyze the inbox log and verify the security ticket code.",
    config=types.GenerateContentConfig(
        temperature=0.2,
        thinking_config=types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.HIGH,  # Options: MINIMAL, LOW, MEDIUM, HIGH
            include_thoughts=True,
        )
    )
)
```

### Configuration Example via LangChain (`langchain-google-genai`)

```python
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    model="gemini-3.8-flash",
    thinking_level="high",      # Supported: "minimal", "low", "medium", "high"
    include_thoughts=True,       # Captures the reasoning trace
    temperature=0.2,
    vertexai=True,
    project="af-aidevs",
    location="global",
)
```

---

## Agentic Best Practices

1. **Explicit System Instructions:**
   Place core task constraints and role definitions at the beginning of `system_prompt.md`.
2. **Iterative Tool Calling & Error Handling:**
   Always enable `handle_tool_error = True` in LangChain agents. Gemini 3.8 Flash excels at autonomous recovery when tools return descriptive errors.
3. **Structured Outputs with Reasoning:**
   Enforce Pydantic schemas with mandatory `reasoning` and `hint` fields to capture the model's decision-making audit trail in BigQuery (`bq`).
4. **Avoid Reflective Suppression:**
   Keep tool prompts objective and concise. Avoid conversational filler in function specifications so the model triggers tool calls promptly.
5. **Session Isolation:**
   Use standardized session identifiers (`{lesson_id}_{backend}_{YYYYMMDD_HHMMSS}`) to correlate audit logs and preserve clean context boundaries.

---

## Migration Notes (from `gemini-3-flash-preview` / `gemini-3.7-flash`)

- **Model String**: Update configuration from `gemini-3-flash-preview` to `gemini-3.8-flash`.
- **API Compatibility**: Fully compatible with Vertex AI `google-genai` and `langchain-google-genai`.
- **Parameter Migration**: Use `thinking_level` (`LOW` / `MEDIUM` / `HIGH`) instead of deprecated legacy thinking budget parameters.
