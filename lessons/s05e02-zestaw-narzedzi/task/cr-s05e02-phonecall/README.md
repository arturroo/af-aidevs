# cr-s05e02-phonecall

Microservice implementing the **S05E02 Phonecall** conversational voice agent.

## Features
- **Deterministic Policy Engine:** Maintains `DialogueState` (Slot-Filling) to ensure the mandatory opening message, authorization challenge (`BARBAKAN`), food transport cover story, and road monitoring deactivation are executed in order.
- **Multimodal Audio Comprehension:** Direct audio input to Gemini 3.8 Flash (`gemini-3.8-flash`) extracting verbatim transcript, sentence-level sentiments/irony/humor, and road statuses.
- **Google Cloud Text-to-Speech:** Uses `pl-PL-Neural2-B` with SSML formatting (`<say-as interpret-as="characters">RD</say-as>`) and accelerated speaking rate (`1.05`) at $0.00 cost under the GCP Free Tier.
- **Dual-Source Call Burn Detection:** Detects call failures via HTTP transport status and single-roundtrip semantic classification with automatic restart recovery up to `max_restarts = 2`.
- **Zero-Pollution Observability:** BigQuery audit streaming to `af-aidevs.s05e02.audit` with Base64 output masking.

## Local Execution

Run CLI mode:
```powershell
uv run python main.py --mode cli --max-iterations 15 --voice-name pl-PL-Neural2-B
```

Run server mode:
```powershell
uv run python main.py --mode server --port 8080
```

## Running Tests

```powershell
uv run pytest -v
```
