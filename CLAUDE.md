# ai-sdlc — single master reference (description + full index)

**Purpose:** One file for humans and AI agents (Claude, Cursor, etc.) that **describes the whole project** and **points to every other artifact** worth opening: docs, diagrams, routes, scripts, tests, prompts, config. Deep detail stays in the linked files; this file is the map and the narrative spine.

**Repository root:** `d:\ai-sdlc` (paths below are **relative to repo root** unless noted.)

---

## Part A — What this project is (full description)

### A.1 Product intent

**ai-sdlc** is a **FastAPI Python backend** that runs an **end-to-end, AI-assisted document pipeline** (internally framed as SDLC-style document generation):

1. Accept **source document** uploads and **Word (.docx) template** uploads.
2. **Ingest** documents: parse (Azure Document Intelligence), **mask PII**, classify images, optional vision extraction, segment, validate, **semantically chunk**, and **vector-index** into **Azure AI Search**.
3. **Prepare templates**: compile / validate / resolve template artifacts so section planning and generation know structure, layout shell, and prompt selection.
4. **Plan sections**: build a `section_plan` (order, titles, retrieval profile, generation strategy, dependencies) and `section_progress`.
5. **Retrieve** per-section **evidence** from the index (with diagnostics and cost-style summaries).
6. **Generate** per-section outputs (text, tables, PlantUML diagrams, etc.) via **Azure OpenAI** routed through a **Semantic Kernel** adapter.
7. **Assemble** all sections into an `assembled_document` and validate completeness.
8. **Render and export** a final **DOCX**, record `output` metadata, expose **download** when status is `READY`.

Execution is **asynchronous**: clients create **workflow runs** over HTTP; work continues in the **background** with **SSE event streams**, **phase-weighted progress**, and **observability** endpoints (cost/diagnostic rollups).

There is **no frontend application** in this repository; only the API and supporting code/docs.

### A.2 Architectural style

**Layered modular monolith** (single deployable service):

| Layer | Path | Role |
|-------|------|------|
| API | `backend/api/` | HTTP routes, schemas, dependencies, error handlers |
| Application | `backend/application/` | Use-case orchestration (`services/`), DTOs (`dto/`) |
| Domain modules | `backend/modules/` | `ingestion`, `retrieval`, `generation`, `template`, `observability` — each with `live_wiring.py` for runtime composition |
| Repositories | `backend/repositories/` | File-backed JSON metadata for workflows, documents, templates, outputs, executions |
| Infrastructure | `backend/infrastructure/` | Azure OpenAI/SK, Search, Document Intelligence, Blob adapters |
| Workers | `backend/workers/` | `TaskDispatcher` — BackgroundTasks → asyncio task → sync fallback |
| Pipeline | `backend/pipeline/` | Planners, ingestion bootstrap/orchestration glue |
| Core | `backend/core/` | Settings, logging, constants, IDs, exceptions, response helpers, request context |
| Prompts | `backend/prompts/` | YAML templates for ingestion, template AI compile, generation strategies |
| Config (static) | `backend/config/` | e.g. `pricing_registry.json` for observability/cost |

**Intended dependency flow:** `api` → `application` → (`repositories` | `workers` | `modules` via bridges); `modules` → `infrastructure`; `core` stays broadly importable and light.

### A.3 Runtime entry

- **Application:** `backend/main.py` — FastAPI app, lifespan (ensures storage dirs), CORS, `register_exception_handlers`, **`X-Request-Id`** middleware.
- **Routes:** `backend/api/router.py` — composes routers under `settings.api_prefix` (default **`/api`** — see `backend/core/config.py`, `backend/core/constants.py`).
- **Settings / env:** `backend/core/config.py`, template env vars in **`backend/.env.example`**.

### A.4 Workflow phases (ordered)

Stable names used in metadata and code:

1. `INPUT_PREPARATION` — progress skeleton, link **ingestion** child execution.
2. `INGESTION` — nine sub-stages (below).
3. `TEMPLATE_PREPARATION` — template bridges / compile readiness.
4. `SECTION_PLANNING` — `section_plan` + `section_progress`.
5. `RETRIEVAL` — `section_retrieval_results`.
6. `GENERATION` — `section_generation_results`.
7. `ASSEMBLY_VALIDATION` — `assembled_document`.
8. `RENDER_EXPORT` — output record + DOCX on disk/blob + `output.ready`.

**Orchestration spine (search these classes):** `WorkflowExecutorService`, `WorkflowService`, `WorkflowEventService`, `IngestionRuntimeBridge`, `IngestionIntegrationService`, `SectionPlanningService`, `SectionProgressService`, `WorkflowSectionRetrievalService`, `WorkflowSectionGenerationService`, `DocumentAssemblyService`, `OutputExportService`, `DocxRendererService` — mapping in **`backend/docs/08_CONNECTION_MAP.md`** and **`backend/docs/PIPELINE_PHASE_SERVICE_OUTPUT_CHEATSHEET.md`**.

### A.5 Ingestion sub-stages (strict order)

1. `01_UPLOAD_AND_DEDUP`  
2. `02_PARSE_DOCUMENT`  
3. `03_MASK_PII`  
4. `04_CLASSIFY_IMAGES`  
5. `05_VISION_EXTRACTION`  
6. `06_SEGMENT_SECTIONS`  
7. `07_VALIDATE_OUTPUTS`  
8. `08_SEMANTIC_CHUNKING`  
9. `09_VECTOR_INDEXING`  

**Code:** `backend/modules/ingestion/stages/`, `backend/modules/ingestion/services/`, `backend/modules/ingestion/contracts/`.

### A.6 Persistence surfaces

- **Local JSON** — workflow runs, executions (`WORKFLOW` + `INGESTION`), documents, templates, outputs; paths from `backend/core/config.py`.
- **Binaries** — uploads, rendered DOCX; may mirror to **Azure Blob** (paths in `.env.example`).
- **Azure AI Search** — retrieval index (chunks + embeddings).
- **`backend/storage/`** — runtime-generated; not source of truth for design.

### A.7 External systems

- Azure OpenAI (chat, reasoning deployments, embeddings)
- Azure AI Document Intelligence
- Azure AI Search
- Azure Blob Storage
- Kroki (diagram rendering; URL in env)

### A.8 AI / LLM conventions

- **Primary adapter:** `backend/infrastructure/ai_clients/sk_unified_adapter.py` (`AzureSemanticKernelTextAdapter`: `invoke_text`, `invoke_json`).
- **Project policy (GPT-5 family):** avoid `temperature` / `max_tokens` on centralized paths; use `reasoning_effort`, completion token budget, `verbosity`, deployment aliases — see **`backend/docs/AI_ORCHESTRATION_MAP.md`**.
- **Prompt files:** `backend/prompts/**/*.yaml` — keys `prompt_template` or `template`; strategy folders may use `default.yaml`.

### A.9 API behavior (cross-cutting)

- Normalized success envelopes and API-layer error mapping — **`backend/api/error_handlers.py`**.
- **`X-Request-Id`** on requests/responses for tracing.

### A.10 Known gaps (read before changing routing)

1. **`backend/api/routes/generation_routes.py`** — standalone `/api/generate-document` job API; **not included** in `backend/api/router.py` (not live unless wired). See **`backend/docs/GO_LIVE_INSPECTION_REPORT.md`**, **`backend/docs/GO_LIVE_TODOS.md`**.
2. **Double `/api` risk** if generation routes keep hardcoded `/api/...` while router already adds `api_prefix`.
3. Nested **`backend/backend/`** storage trees may appear in some dev environments — treat as generated output.

---

## Part B — Complete documentation index (`backend/docs/`)

Hub and reading order: **`backend/docs/README.md`**

### B.1 Numbered core docs

| # | File | Topic |
|---|------|--------|
| 01 | `backend/docs/01_PROJECT_OVERVIEW.md` | Business purpose, layers, phases, integrations |
| 02 | `backend/docs/02_FOLDER_GUIDE.md` | Folder ownership, dependency rules |
| 03 | `backend/docs/03_FILE_CATALOG_CORE_API_APP.md` | File-level catalog: core, api, application, repositories, workers, infrastructure |
| 04 | `backend/docs/04_FILE_CATALOG_MODULES.md` | File-level catalog: modules, pipeline |
| 05 | `backend/docs/05_STAGE_AND_API_REFERENCE.md` | Stages ↔ HTTP endpoints |
| 06 | `backend/docs/06_DATA_STORAGE_AND_STATE.md` | Persistence, records, state machines |
| 07 | `backend/docs/07_OPERATIONS_AND_RUNBOOK.md` | Env, run commands, verification, troubleshooting |
| 08 | `backend/docs/08_CONNECTION_MAP.md` | Folders ↔ services ↔ stages |
| 09 | `backend/docs/09_TESTS_DOCUMENTATION.md` | Test layout and intent |
| 10 | `backend/docs/10_PROMPTS_DOCUMENTATION.md` | Prompt inventory and conventions |
| 11 | `backend/docs/11_SCRIPTS_AND_UTILITIES.md` | Script catalog |
| 12 | `backend/docs/12_CONFIG_AND_PRICING_REFERENCE.md` | Static config, pricing registry |
| 13 | `backend/docs/13_API_EXAMPLES.md` | cURL / request-response examples |
| 14 | `backend/docs/14_ONBOARDING_QUICKSTART.md` | Setup → first workflow |
| 15 | `backend/docs/15_CONTRIBUTION_GUIDE.md` | Contribution workflow |

### B.2 Pipeline / AI / go-live docs

| File | Topic |
|------|--------|
| `backend/docs/PIPELINE_PHASE_SERVICE_OUTPUT_CHEATSHEET.md` | **Phase → service class → artifact** (execution ground truth) |
| `backend/docs/AI_ORCHESTRATION_MAP.md` | Where LLMs/embeddings run; SK adapter; GPT-5 policy |
| `backend/docs/PROJECT_DIAGRAMS_MASTER_GUIDE.md` | Diagram strategy and how to read diagrams |
| `backend/docs/GO_LIVE_INSPECTION_REPORT.md` | Readiness / gaps audit |
| `backend/docs/GO_LIVE_TODOS.md` | Action checklist for go-live |

### B.3 Diagrams (`backend/docs/diagrams/`)

| File | Topic (from filename / doc set) |
|------|----------------------------------|
| `backend/docs/diagrams/01-system-context.md` | System context |
| `backend/docs/diagrams/02-container-architecture.md` | Containers |
| `backend/docs/diagrams/03-layered-architecture.md` | Layers |
| `backend/docs/diagrams/04-workflow-phases.md` | Workflow phases |
| `backend/docs/diagrams/05-ingestion-pipeline.md` | Ingestion |
| `backend/docs/diagrams/06-retrieval-flow.md` | Retrieval |
| `backend/docs/diagrams/07-generation-flow.md` | Generation |
| `backend/docs/diagrams/08-assembly-export-flow.md` | Assembly / export |
| `backend/docs/diagrams/09-state-machine-workflow.md` | Workflow state machine |
| `backend/docs/diagrams/10-state-machine-ingestion.md` | Ingestion state machine |
| `backend/docs/diagrams/11-data-lifecycle.md` | Data lifecycle |
| `backend/docs/diagrams/12-storage-layout.md` | Storage layout |
| `backend/docs/diagrams/13-api-sequence-create-workflow.md` | API sequence: create workflow |
| `backend/docs/diagrams/14-deployment-topology.md` | Deployment |
| `backend/docs/diagrams/15-observability-model.md` | Observability |
| `backend/docs/diagrams/16-threat-model.md` | Threat model |

---

## Part C — Repository root and planning artifacts

| File | Topic |
|------|--------|
| `CLAUDE.md` | **This file** — master description + full index |
| `plan.md.txt` | Planning notes / roadmap content (text; not part of `backend/docs` hub) |
| `.gitignore` | Git ignore rules |

---

## Part D — Backend package: entry points and wiring

| File | Role |
|------|------|
| `backend/main.py` | FastAPI app entry |
| `backend/__init__.py` | Package marker |
| `backend/api/router.py` | Mounts all **live** API routers under `api_prefix` |
| `backend/api/dependencies.py` | Shared DI |
| `backend/api/error_handlers.py` | Exception → HTTP mapping |
| `backend/core/config.py` | Pydantic settings |
| `backend/core/constants.py` | Defaults (API prefix, dirs, etc.) |
| `backend/requirements.txt` | Runtime dependencies |
| `backend/requirements-dev.txt` | Dev/test dependencies |
| `backend/pytest.ini` | Pytest config (`pythonpath`, asyncio) |
| `backend/.env.example` | Environment variable template (copy to `.env`) |

---

## Part E — HTTP routes (Python modules)

**Mounted from `backend/api/router.py`:**

| File | Area |
|------|------|
| `backend/api/routes/health_routes.py` | `/health`, `/ready` |
| `backend/api/routes/document_routes.py` | Documents CRUD + upload |
| `backend/api/routes/template_routes.py` | Templates, compile, validate, resolve, downloads |
| `backend/api/routes/workflow_routes.py` | Workflow runs create/list/get/status/sections/observability |
| `backend/api/routes/workflow_event_routes.py` | SSE workflow events |
| `backend/api/routes/workflow_inspection_routes.py` | Events snapshot, errors, artifacts, diagnostics |
| `backend/api/routes/output_routes.py` | Output metadata + download |

**Exists but not mounted on main router (see Part A.10):**

| File |
|------|
| `backend/api/routes/generation_routes.py` |

**Schemas:** `backend/api/schemas/`  
**Endpoint catalog:** `backend/docs/05_STAGE_AND_API_REFERENCE.md` and `backend/docs/13_API_EXAMPLES.md`.

---

## Part F — Scripts (`backend/scripts/`)

| File |
|------|
| `backend/scripts/cleanup_blob_test_artifacts.py` |
| `backend/scripts/create_ai_search_index.py` |
| `backend/scripts/generate_placeholder_docx.py` |
| `backend/scripts/rebuild_docx_from_extraction.py` |
| `backend/scripts/retrieval_live_smoke.py` |
| `backend/scripts/run_ingestion.py` |
| `backend/scripts/run_mock_e2e_integration.py` |
| `backend/scripts/run_retrieval_integration.py` |
| `backend/scripts/run_template_azure_smoke.py` |
| `backend/scripts/smoke_test.py` |
| `backend/scripts/staging_workflow_e2e.py` |
| `backend/scripts/test_docx_structure_extraction.py` |
| `backend/scripts/test_phase1.py` |
| `backend/scripts/test_phase2_template_bridge.py` |
| `backend/scripts/test_phase3_retrieval_generation_bridge.py` |
| `backend/scripts/test_phase4_rendering.py` |
| `backend/scripts/verify_endpoints.py` |
| `backend/scripts/verify_lifecycle.py` |

**Script narrative and usage:** `backend/docs/11_SCRIPTS_AND_UTILITIES.md`.

---

## Part G — Manual testing (`backend/manual_testing/`)

| File |
|------|
| `backend/manual_testing/README.md` |
| `backend/manual_testing/common.py` |
| `backend/manual_testing/run_assembly_export_manual.py` |
| `backend/manual_testing/run_generation_manual.py` |
| `backend/manual_testing/run_ingestion_manual.py` |
| `backend/manual_testing/run_retrieval_manual.py` |
| `backend/manual_testing/run_section_planning_manual.py` |
| `backend/manual_testing/run_template_preparation_manual.py` |
| `backend/manual_testing/run_workflow_stagewise_manual.py` |
| `backend/manual_testing/__init__.py` |

---

## Part H — Automated tests (`backend/tests/`)

**Config / shared:** `backend/tests/conftest.py`

**Integration:**

| File |
|------|
| `backend/tests/integration/test_api_endpoints.py` |
| `backend/tests/integration/test_template_to_workflow.py` |
| `backend/tests/integration/test_workflow_lifecycle.py` |
| `backend/tests/integration/modules/ingestion/test_ingestion_pipeline.py` |
| `backend/tests/integration/modules/generation/test_generation_pipeline.py` |
| `backend/tests/integration/modules/retrieval/test_retrieval_pipeline.py` |

**Unit (representative tree — see also `backend/docs/09_TESTS_DOCUMENTATION.md`):**

- `backend/tests/unit/api/test_api_layer.py`
- `backend/tests/unit/application/dto/test_dtos.py`
- `backend/tests/unit/application/services/test_app_services.py`
- `backend/tests/unit/application/services/test_workflow_section_retrieval_service.py`
- `backend/tests/unit/core/` — `test_config.py`, `test_constants.py`, `test_exceptions.py`, `test_ids.py`, `test_logging.py`, `test_request_context.py`, `test_response.py`
- `backend/tests/unit/modules/generation/` — `test_assembly.py`, `test_generation_contracts.py`, `test_generators.py`, `test_output_validator.py`, `__init__.py`
- `backend/tests/unit/modules/ingestion/` — contracts, chunking, parser, pii, repo, segmentation, upload, validation, etc.
- `backend/tests/unit/modules/observability/test_observability.py`
- `backend/tests/unit/modules/retrieval/` — contracts, evidence packager, query builder, reranker, vector search
- `backend/tests/unit/modules/template/` — contracts, loader, models, repo, resolver, validator, dependency sorter, compiler tests under `test_compiler/`
- `backend/tests/unit/pipeline/` — `test_progress_planner.py`, `test_section_execution_planner.py`
- `backend/tests/unit/repositories/` — document, execution, output, template, workflow repos
- `backend/tests/unit/workers/` — `test_background_runner.py`, `test_task_dispatcher.py`

---

## Part I — Prompts (`backend/prompts/`)

**Ingestion**

| File |
|------|
| `backend/prompts/ingestion/pii_classification_v1.yaml` |
| `backend/prompts/ingestion/vision_generic_v1.yaml` |

**Template**

| File |
|------|
| `backend/prompts/template/ai_compiler_v1.yaml` |
| `backend/prompts/template/correction_loop_v1.yaml` |

**Generation — `summarize_text/`** (examples; folder also contains `default.yaml`, `architecture.yaml`, `requirements.yaml`, … full list in repo)

| File |
|------|
| `backend/prompts/generation/summarize_text/acceptance_criteria.yaml` |
| `backend/prompts/generation/summarize_text/architecture.yaml` |
| `backend/prompts/generation/summarize_text/assumptions.yaml` |
| `backend/prompts/generation/summarize_text/compliance_controls.yaml` |
| `backend/prompts/generation/summarize_text/constraints.yaml` |
| `backend/prompts/generation/summarize_text/data_flow.yaml` |
| `backend/prompts/generation/summarize_text/default.yaml` |
| `backend/prompts/generation/summarize_text/deployment_strategy.yaml` |
| `backend/prompts/generation/summarize_text/integration_points.yaml` |
| `backend/prompts/generation/summarize_text/non_functional_requirements.yaml` |
| `backend/prompts/generation/summarize_text/operational_readiness.yaml` |
| `backend/prompts/generation/summarize_text/operations_runbook.yaml` |
| `backend/prompts/generation/summarize_text/overview.yaml` |
| `backend/prompts/generation/summarize_text/requirements.yaml` |
| `backend/prompts/generation/summarize_text/risks.yaml` |
| `backend/prompts/generation/summarize_text/scope.yaml` |
| `backend/prompts/generation/summarize_text/security_controls.yaml` |
| `backend/prompts/generation/summarize_text/system_design.yaml` |
| `backend/prompts/generation/summarize_text/system_overview.yaml` |

**Generation — `generate_table/`**

| File |
|------|
| `backend/prompts/generation/generate_table/api_matrix.yaml` |
| `backend/prompts/generation/generate_table/api_specification.yaml` |
| `backend/prompts/generation/generate_table/catalog.yaml` |
| `backend/prompts/generation/generate_table/data_model.yaml` |
| `backend/prompts/generation/generate_table/default.yaml` |
| `backend/prompts/generation/generate_table/integration_matrix.yaml` |
| `backend/prompts/generation/generate_table/mapping.yaml` |
| `backend/prompts/generation/generate_table/matrix.yaml` |
| `backend/prompts/generation/generate_table/nfr_matrix.yaml` |
| `backend/prompts/generation/generate_table/risk_register_table.yaml` |
| `backend/prompts/generation/generate_table/test_coverage.yaml` |
| `backend/prompts/generation/generate_table/traceability_matrix.yaml` |

**Generation — `diagram_plantuml/`**

| File |
|------|
| `backend/prompts/generation/diagram_plantuml/architecture.yaml` |
| `backend/prompts/generation/diagram_plantuml/component.yaml` |
| `backend/prompts/generation/diagram_plantuml/data_flow_diagram.yaml` |
| `backend/prompts/generation/diagram_plantuml/default.yaml` |
| `backend/prompts/generation/diagram_plantuml/deployment.yaml` |
| `backend/prompts/generation/diagram_plantuml/flowchart.yaml` |
| `backend/prompts/generation/diagram_plantuml/sequence.yaml` |
| `backend/prompts/generation/diagram_plantuml/system_context_diagram.yaml` |

**Prompt documentation:** `backend/docs/10_PROMPTS_DOCUMENTATION.md`.

---

## Part J — Static config

| File |
|------|
| `backend/config/pricing_registry.json` |

**Reference:** `backend/docs/12_CONFIG_AND_PRICING_REFERENCE.md`.

---

## Part K — How agents should use this file

1. **Read Part A** for behavior, phases, persistence, and caveats.  
2. **Open `backend/docs/PIPELINE_PHASE_SERVICE_OUTPUT_CHEATSHEET.md`** when debugging execution order or missing artifacts.  
3. **Use Part B** to jump to the exact markdown you need (file catalogs, API examples, ops).  
4. **Use Parts D–J** as a filesystem checklist: routes, scripts, tests, prompts, config.  
5. **Do not duplicate** long tables from `03_*` and `04_*` file catalogs here — those docs are the line-by-line source listings.

---

## Part L — One-paragraph summary

**ai-sdlc** is a FastAPI service under `backend/` that orchestrates a multi-phase workflow (ingestion with nine sub-stages, template preparation, section planning, retrieval from Azure AI Search, LLM generation via a Semantic Kernel adapter, assembly, and DOCX export), persists rich metadata as local JSON, streams workflow events over SSE, aggregates observability, integrates Azure OpenAI, Document Intelligence, Search, and Blob, and documents every stage, file, and diagram under `backend/docs/` — with this **`CLAUDE.md`** as the single entry point that references all of the above.
