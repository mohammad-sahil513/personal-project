# AI Orchestration Map

This document describes where AI/LLM calls happen in the backend pipeline and how they are wired.

It reflects the current centralized Semantic Kernel adapter approach and the GPT-5/GPT-5-mini parameter policy.

---

## Global policy (GPT-5 / GPT-5-mini)

Across centralized LLM paths:

- Do not use `temperature`
- Do not use `max_tokens`
- Use alternatives:
  - `reasoning_effort` (`low|medium|high`)
  - `response_token_budget` mapped to `max_completion_tokens`
  - `verbosity` as instruction-level guidance
  - `model_preference` / deployment alias selection

---

## Shared adapter core

Primary shared adapter:

- `backend/infrastructure/ai_clients/sk_unified_adapter.py`
  - `AzureSemanticKernelTextAdapter.invoke_text(...)`
  - `AzureSemanticKernelTextAdapter.invoke_json(...)`

Used by:

- Generation runtime live wiring
- Template compiler structured adapter
- Ingestion Stage-3 prompt executor (bootstrap path)

---

## Pipeline map

## Ingestion pipeline

- **Stage 3: PII classification**
  - Stage: `backend/modules/ingestion/stages/03_mask_pii.py`
  - Service: `backend/modules/ingestion/services/pii_service.py`
  - Classifier adapter: `backend/modules/ingestion/services/pii_classifier_adapter.py`
  - Prompt executor wiring: `backend/pipeline/bootstrap/ingestion_bootstrap.py`
  - Prompt file: `backend/prompts/ingestion/pii_classification_v1.yaml`
  - LLM backend: shared SK adapter via `LiveSemanticKernelPromptExecutor`

- **Stage 5: Vision extraction**
  - Service: `backend/modules/ingestion/services/vision_extraction_service.py`
  - Current bootstrap uses deterministic extractor (`LocalSmokeVisionExtractor`)
  - No centralized LLM call in current bootstrap implementation

- **Stage 9: Vector indexing embeddings**
  - Stage: `backend/modules/ingestion/stages/09_vector_indexing.py`
  - Service: `backend/modules/ingestion/services/indexing_service.py`
  - Uses Azure OpenAI embeddings client (`AsyncAzureOpenAI.embeddings.create`)
  - This is AI usage but embedding-specific, not SK chat prompt orchestration

---

## Template compiler flow

- Orchestrator: `backend/modules/template/compiler/compiler_orchestrator.py`
- AI mapping: `backend/modules/template/compiler/ai_compiler.py`
- AI correction: `backend/modules/template/compiler/correction_loop.py`
- Structured adapter wrapper:
  - `backend/modules/template/compiler/azure_sk_structured_adapter.py`
  - Internally delegates to shared `AzureSemanticKernelTextAdapter.invoke_json(...)`

Prompt files:

- `backend/prompts/template/ai_compiler_v1.yaml`
- `backend/prompts/template/correction_loop_v1.yaml`

---

## Generation flow

- Runtime bridge: `backend/application/services/generation_runtime_bridge.py`
- Live wiring: `backend/modules/generation/live_wiring.py`
- Section orchestration: `backend/modules/generation/orchestrators/section_executor.py`
- Generators:
  - `backend/modules/generation/generators/text_generator.py`
  - `backend/modules/generation/generators/table_generator.py`
  - `backend/modules/generation/generators/diagram_generator.py`
- Diagram repair: `backend/modules/generation/diagram/repair_loop.py`

LLM backend in live wiring now uses shared SK adapter:

- `AzureSemanticKernelTextAdapter.invoke_text(...)`

Prompt assembly and resolution:

- Assembler: `backend/modules/generation/generators/prompt_assembler.py`
- Prompt selector: `backend/modules/template/services/prompt_selector_service.py`
- Prompt folders:
  - `backend/prompts/generation/summarize_text/*.yaml`
  - `backend/prompts/generation/generate_table/*.yaml`
  - `backend/prompts/generation/diagram_plantuml/*.yaml`

---

## Prompt artifact conventions

- Prompt files are YAML under `backend/prompts/**`
- Expected body keys:
  - `prompt_template` (preferred)
  - `template` (supported alias)
- Strategy folders support fallback to `default.yaml` where implemented

---

## Quick maintenance checklist

- When adding a new LLM feature:
  - Reuse `AzureSemanticKernelTextAdapter` unless there is a strong reason not to
  - Keep GPT-5 policy (no `temperature`, no `max_tokens`)
  - Add/update prompt YAML in the correct strategy/folder
  - Ensure model hint fields align with existing execution hints schema
  - Add/update tests for the affected module path

- When debugging LLM behavior:
  - Verify selected prompt key and resolved prompt file
  - Verify deployment alias mapping (`gpt5mini` / `gpt5`)
  - Verify `reasoning_effort` and response budget passed through
  - Confirm structured calls return valid JSON where required
