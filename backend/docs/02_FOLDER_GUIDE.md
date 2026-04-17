# 02 - Folder Guide

## Top-Level Backend Folders

## `api/`
- Responsibility: HTTP API surface (routes, schemas, shared dependencies).
- Contains route handlers for documents, templates, workflows, outputs, health, and generation.

## `application/`
- Responsibility: high-level use-case orchestration.
- `services/`: workflow orchestration, bridges, progress, assembly, export.
- `dto/`: typed data transfer objects used between layers.

## `core/`
- Responsibility: shared foundation utilities.
- Config, constants, logging, request context, error model, and response helper.

## `repositories/`
- Responsibility: primary metadata persistence adapters (file-based).
- Manages workflow/document/template/output/execution records.

## `infrastructure/`
- Responsibility: external SDK adapters and cloud API translation.
- Azure OpenAI and Azure Search adapters live here.

## `workers/`
- Responsibility: background dispatch abstraction.
- Unified async/sync task execution strategy and dispatch-mode selection.

## `modules/`
- Responsibility: domain-heavy logic grouped by bounded context.
- `ingestion/`, `retrieval/`, `generation/`, `template/`, `observability/`.

## `pipeline/`
- Responsibility: orchestration helpers and planners.
- Progress planning, section execution planning, and ingestion orchestration scaffold.

## `docs/`
- Responsibility: all architecture, operations, API, and diagram documentation.

## `tests/`
- Responsibility: unit and integration coverage for API, services, modules, and planners.

## `prompts/`
- Responsibility: prompt templates used by ingestion/generation/template compile paths.

## `scripts/`
- Responsibility: local smoke/e2e helper scripts.

## `config/`
- Responsibility: static runtime data, such as pricing registry.

## `storage/` (runtime data)
- Responsibility: runtime-generated local metadata and artifacts.
- Not source code; generated during execution.

---

## Folder Interaction Rules (Intended)

- `api` calls `application/services`.
- `application/services` can call:
  - `repositories`
  - `workers`
  - `infrastructure` (via bridges/wiring)
  - `modules/*` orchestration entry points
- `modules/*` contain domain internals and can use module-local repositories/contracts.
- `core` is shared and should remain dependency-light.

---

## Documentation Coverage Mapping

- File-level details for `core`, `api`, `application`, `repositories`, `workers`, `infrastructure`:
  - `03_FILE_CATALOG_CORE_API_APP.md`
- File-level details for `modules` and `pipeline`:
  - `04_FILE_CATALOG_MODULES.md`
- End-to-end stage and endpoint mapping:
  - `05_STAGE_AND_API_REFERENCE.md`
