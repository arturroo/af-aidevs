# PRD - S01E04 Task: sendit

## Objective
Automate the process of filling out a transport declaration in the "System Przesyłek Konduktorskich" (SPK) to successfully complete the `sendit` task from the AI_Devs course. The final result must be a correctly formatted string sent to the verification endpoint.

## Context
The task requires navigating through a complex, multi-file documentation set (mostly Markdown and images) hosted on a remote hub. The documentation contains rules for:
- Route codes.
- Category classification.
- Fee calculation (must result in 0 PP).
- Declaration formatting (strict template).

> [!IMPORTANT]
> **Secret Hint**: "Myśleli, że to usunęli, ale to zostało w mojej GŁOWIE"
> (They thought they deleted it, but it stayed in my HEAD). 
> This suggests that critical information might be hidden in **HTML `<head>` tags**, document metadata, or "removed" files that are still accessible.

## Functional Requirements
1. **Multimodal Documentation Parsing**: 
   - Download the root `index.md` from the documentation hub.
   - Identify and recursively download all linked files (Markdown, Images).
   - Use Vision capabilities (Gemini 3 Flash) to extract information from images (e.g., maps, route lists).
2. **Information Extraction & Reasoning**:
   - Determine the correct **Route Code** for the Gdańsk - Żarnowiec path.
   - Identify the appropriate **Category** for "kasety z paliwem do reaktora" that allows for a **0 PP** fee (likely Category A - Strategiczna).
   - Locate the **Declaration Template** and adhere to its exact structure and separators.
3. **Declaration Generation**:
   - Use an LLM to fill the template with the provided data:
     - Nadawca: 450202122
     - Punkt nadawczy: Gdańsk
     - Punkt docelowy: Żarnowiec
     - Waga: 2800 kg
     - Zawartość: kasety z paliwem do reaktora
     - Uwagi: brak
     - Route Code: (to be discovered)
     - Budget/Fee: 0 PP
4. **Verification**:
   - Send the generated declaration string to `$AIDEVS_VERIFY` with task name `sendit`.

## Non-Functional Requirements
- **Technology Stack**: Python with `uv`.
- **Frameworks**: LangChain (default) and Vertex AI SDK (ADK) as an alternative.
- **Observability**: Integrate LangSmith for tracing (LangChain) and appropriate logging for ADK.
- **Environment Variables**: Use `.env` for `$AIDEVS_VERIFY`, `$AIDEVS_API_KEY`, and `$AIDEVS_DOC`.
- **Modularity**: Separation of concerns between scraping, reasoning, and submission.

## Architecture & Workflow
1. **Phase 1: Knowledge Discovery (Agent Loop)**
   - Start with `index.md`.
   - Tool-use: `fetch_document(path)`, `analyze_image(path)`.
   - Agent builds an internal representation of the rules.
2. **Phase 2: Declaration Crafting**
   - Agent uses the gathered knowledge to fill the template.
3. **Phase 3: Validation & Submission**
   - Final check against the rules.
   - Post to verification server.

## Cloud Resources
- None required (no Terraform). The task is purely logical/API-driven.

## TODO / Artur's Input
- [ ] **[ARTUR TO FILL]**: Specific edge cases or hidden rules discovered during manual exploration.
- [ ] **[ARTUR TO FILL]**: Refinement of the system message for the agent loop.
