# Repository Backlog & Architectural TODOs

This backlog tracks planned architectural refactorings, optimizations, and technical debt across the `af-aidevs` repository.

---

## Active Backlog Items

### [ARCH-001] Refactor `cr-mcp-workspace.read_binary_file` to Claim-Check Pattern with Temporary GCS Signed URLs
- **Status:** Backlog / Ready for Implementation
- **Priority:** High (Architectural & Cost Optimization)
- **Target Component:** `cr-mcp-workspace` (Cloud Run MCP Workspace Service)
- **Date Added:** 2026-09-16
- **Assigned To:** Artur Fejklowicz & Joi
- **Reference:** [BEST_PRACTICES.md](BEST_PRACTICES.md) Section 1.2

#### Problem Description
Currently, `cr-mcp-workspace` implements `read_binary_file` by reading binary files from Cloud Storage (`gs://af-aidevs-workspaces/...`) and returning the entire content as an In-Band Base64 string inside the JSON-RPC response payload:
```json
{
  "status": "success",
  "content_base64": "U1FMaXRlIGZvcm1hdCAzABAAAgIAQCAgAAAAAgACc0..."
}
```
This design creates multiple production risks:
1. **Serialization Overhead:** Base64 inflates the wire payload by $+33.3\%$ compared to raw binary.
2. **JSON Parser & Memory Stress:** Large JSON-RPC strings (e.g. 10–50 MB SQLite databases or archives) consume excessive heap memory during serialization and deserialization in Python.
3. **Telemetry & Log Exposure:** Unless explicitly masked, downstream agent frameworks (LangChain, LangSmith, Langfuse) capture the multi-megabyte string in traces, leading to telemetry poisoning and UI lag.

#### Target Implementation (Best Practice Standard)
Refactor `read_binary_file` (and related binary endpoints in `cr-mcp-workspace`) to implement the **Claim-Check Pattern** using Google Cloud Storage **V4 Signed URLs**:
1. When `read_binary_file` is invoked, the service generates a time-bounded V4 Signed URL using its own Cloud Run Service Account credentials (`sa-cr-mcp-workspace`):
   ```python
   signed_url = blob.generate_signed_url(
       version="v4",
       expiration=datetime.timedelta(minutes=2),
       method="GET",
   )
   ```
2. The MCP tool returns a lightweight metadata ticket instead of the raw Base64 payload:
   ```json
   {
     "status": "success",
     "file_path": "inventory.db",
     "signed_url": "https://storage.googleapis.com/af-aidevs-workspaces/shared/s03e04/inventory.db?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=...&X-Goog-Expires=120...",
     "expires_in_seconds": 120,
     "size_bytes": 10485760,
     "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
   }
   ```
3. **Consumer Benefits:**
   - **Zero IAM Overhead:** Consumers download the binary over standard HTTPS `GET` (via `curl` or `httpx`) without needing any GCP credentials or IAM permissions.
   - **Strict 2-Minute Exposure:** The signed URL expires in 120 seconds, returning `HTTP 403 Forbidden` thereafter.
   - **Zero Telemetry Bloat:** Observability platforms log only the lightweight URL ticket, completely eliminating megabyte dumps.

---

### [ARCH-002] Investigate Asynchronous Traffic Smoothing via `aiolimiter` for Vertex AI Microservices
- **Status:** Backlog / Under Investigation
- **Priority:** Medium (Resilience & Throughput Engineering)
- **Target Component:** Shared agent microservices & tool pipelines (`af_aidevs`)
- **Date Added:** 2026-09-16
- **Assigned To:** Artur Fejklowicz & Joi
- **Reference:** [BEST_PRACTICES.md](BEST_PRACTICES.md) Section 4.2 & [Google Cloud Blog: Reduce 429 Errors](https://cloud.google.com/blog/products/ai-machine-learning/reduce-429-errors-on-vertex-ai)

#### Problem Description
Under Vertex AI Standard PayGo, models (such as `gemini-3.8-flash` in `global`) are subject to sub-second micro-burst rate limiting. Even when average token throughput is well within the 2,000,000 TPM baseline, rapid consecutive LLM invocations in agent pipelines (e.g. pre-flight extraction immediately followed by post-flight synthesis within 1–2 seconds) trigger transient `429 RESOURCE_EXHAUSTED` errors. While hardcoded `sleep()` is an architectural anti-pattern that burns Cloud Run vCPU-seconds and threatens client timeouts, unmitigated bursts can induce retry storms.

#### Research & Implementation Scope
Investigate implementing a non-blocking asynchronous Token Bucket rate limiter using `aiolimiter` (or equivalent asyncio queue):
1. **Zero-Wait Normal Operation:** When traffic is below burst thresholds, requests execute with zero artificial latency.
2. **Graceful Queueing on Bursts:** Under sudden concurrency spikes, `AsyncLimiter(max_rate=N, time_period=M)` smoothly spreads requests across second intervals without thread blocking.
3. **Benchmarking:** Measure tail latency ($P_{99}$) and 429 incidence on Cloud Run under concurrent agent load.
