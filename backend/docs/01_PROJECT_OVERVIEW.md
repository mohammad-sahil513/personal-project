# 01 - Project Overview

## What This Backend Does

This backend orchestrates an end-to-end document workflow:

1. Accept document and template uploads.
2. Run ingestion on documents (parse, mask PII, chunk, index).
3. Build section plans from templates.
4. Retrieve evidence per section.
5. Generate section outputs.
6. Assemble sections into a final document.
7. Export DOCX and expose output download APIs.

It supports asynchronous execution, workflow tracking, event streaming, and
observability summaries (progress + cost + diagnostics).

## Architecture Style

The codebase uses a layered and modular architecture:

- **API layer** (`backend/api`): route handlers, request contracts, response mapping.
- **Application layer** (`backend/application/services`): workflow/business orchestration.
- **Domain modules** (`backend/modules/*`): ingestion/retrieval/generation/template logic.
- **Repositories** (`backend/repositories`, plus module repositories): metadata persistence.
- **Infrastructure adapters** (`backend/infrastructure`): Azure OpenAI/Search integrations.
- **Workers** (`backend/workers`): async task dispatch and execution wrapper.
- **Pipeline helpers** (`backend/pipeline`): planners and ingestion orchestrator wiring.
- **Core shared utilities** (`backend/core`): config, logging, exceptions, IDs, response contracts.

## Runtime Entry

- Entrypoint: `backend/main.py`
- API composition: `backend/api/router.py`
- API prefix and environment loaded from `backend/core/config.py`

## Workflow Phase Order

1. `INPUT_PREPARATION`
2. `INGESTION`
3. `TEMPLATE_PREPARATION`
4. `SECTION_PLANNING`
5. `RETRIEVAL`
6. `GENERATION`
7. `ASSEMBLY_VALIDATION`
8. `RENDER_EXPORT`

## Ingestion Sub-Stages

1. `01_UPLOAD_AND_DEDUP`
2. `02_PARSE_DOCUMENT`
3. `03_MASK_PII`
4. `04_CLASSIFY_IMAGES`
5. `05_VISION_EXTRACTION`
6. `06_SEGMENT_SECTIONS`
7. `07_VALIDATE_OUTPUTS`
8. `08_SEMANTIC_CHUNKING`
9. `09_VECTOR_INDEXING`

## External Integrations

- Azure OpenAI
- Azure AI Search
- Azure Document Intelligence
- Azure Blob Storage

## Persistence Model (Current)

- Local JSON-based metadata records for workflow, execution, documents, templates, outputs.
- Binary and output artifact files on local filesystem.
- Indexed retrieval data in Azure AI Search.

## Who Should Read What

- New developer onboarding: `README.md`, `02_FOLDER_GUIDE.md`, `05_STAGE_AND_API_REFERENCE.md`.
- API consumers: `05_STAGE_AND_API_REFERENCE.md`.
- Platform/ops: `06_DATA_STORAGE_AND_STATE.md`, `07_OPERATIONS_AND_RUNBOOK.md`.
- Architecture review: `PROJECT_DIAGRAMS_MASTER_GUIDE.md` + `docs/diagrams/*`.
