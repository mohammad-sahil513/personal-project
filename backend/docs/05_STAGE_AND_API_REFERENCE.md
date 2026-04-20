# 05 - Stage and API Reference

This document maps API endpoints to workflow stages and internal service flows.

## Workflow Stage Reference

## 1. `INPUT_PREPARATION`
- Initializes phase structure and creates/links ingestion execution.
- Core service: `WorkflowExecutorService`.

## 2. `INGESTION`
- Runs 9 ingestion sub-stages and tracks ingestion execution metadata.
- Core services: `IngestionRuntimeBridge`, `IngestionIntegrationService`.

## 3. `TEMPLATE_PREPARATION`
- Ensures template context readiness before section planning/generation.
- Core services: template app/compile/resolve bridges.

## 4. `SECTION_PLANNING`
- Creates section plan and section progress model.
- Core services: `SectionPlanningService`, `SectionProgressService`.

## 5. `RETRIEVAL`
- Retrieves evidence per section.
- Core services: `WorkflowSectionRetrievalService`, retrieval module runtime.

## 6. `GENERATION`
- Generates section outputs per section.
- Core services: `WorkflowSectionGenerationService`, generation runtime.

## 7. `ASSEMBLY_VALIDATION`
- Assembles generated sections into document structure.
- Core service: `DocumentAssemblyService`.

## 8. `RENDER_EXPORT`
- Prepares output record and renders DOCX artifact.
- Core services: `OutputExportService`, `DocxRendererService`.

---

## API Endpoint Catalog (Stage-Aligned)

## Health

- `GET /health`
  - Purpose: liveness check.
  - Stage relation: platform-level (no stage).
- `GET /ready`
  - Purpose: readiness and configuration visibility.
  - Stage relation: platform-level (no stage).

## Documents

- `POST /documents/upload`
  - Purpose: upload document binary and create document metadata.
  - Stage relation: pre-workflow input asset creation.
- `GET /documents`
  - Purpose: list documents.
- `GET /documents/{document_id}`
  - Purpose: fetch document metadata.
- `DELETE /documents/{document_id}`
  - Purpose: delete document metadata and binary.

## Templates

- `POST /templates/upload`
  - Purpose: upload template and create template metadata.
  - Stage relation: pre-workflow template setup.
- `GET /templates`
- `GET /templates/{template_id}`
- `GET /templates/{template_id}/download`
  - Purpose: download raw uploaded template DOCX (used by frontend preview popup).
  - Stage relation: pre-workflow template inspection.
- `POST /templates/{template_id}/compile`
  - Purpose: async template compile dispatch.
  - Stage relation: template preparation.
- `GET /templates/{template_id}/compile-status`
- `GET /templates/{template_id}/compiled`
- `POST /templates/{template_id}/validate`
- `POST /templates/{template_id}/resolve`
- `GET /templates/{template_id}/manifest/download`
- `GET /templates/{template_id}/shell/download`

## Workflow Runs

- `POST /workflow-runs`
  - Purpose: create workflow run; optionally start execution immediately.
  - Stage relation: enters `INPUT_PREPARATION` if started.
- `GET /workflow-runs`
  - Purpose: list workflow runs.
- `GET /workflow-runs/{workflow_run_id}`
  - Purpose: fetch full workflow metadata.
- `GET /workflow-runs/{workflow_run_id}/status`
  - Purpose: stage-aware status with current label and ingestion block.
- `GET /workflow-runs/{workflow_run_id}/sections`
  - Purpose: fetch section plan details.
- `GET /workflow-runs/{workflow_run_id}/observability`
  - Purpose: retrieval/generation/ingestion cost and phase breakdown summaries.

## Workflow Events and Inspection

- `GET /workflow-runs/{workflow_run_id}/events`
  - Purpose: live SSE stream of workflow events.
- `GET /workflow-runs/{workflow_run_id}/events/snapshot`
  - Purpose: recent events snapshot for inspection.
- `GET /workflow-runs/{workflow_run_id}/errors`
  - Purpose: aggregated workflow errors.
- `GET /workflow-runs/{workflow_run_id}/artifacts`
  - Purpose: workflow artifact references.
- `GET /workflow-runs/{workflow_run_id}/diagnostics`
  - Purpose: workflow diagnostics summary.

## Outputs

- `GET /outputs/{output_id}`
  - Purpose: output metadata and readiness status.
  - Stage relation: `RENDER_EXPORT` / final artifact lifecycle.
- `GET /outputs/{output_id}/download`
  - Purpose: download final DOCX when status is `READY`.

## Generation Module API (Dedicated)

- `POST /api/generate-document`
  - Purpose: start generation job for generation module pipeline.
- `GET /api/generate-document/{job_id}/status`
  - Purpose: generation job status.
- `GET /api/generate-document/{job_id}/events`
  - Purpose: generation SSE event stream with replay/poll controls.

---

## Stage-to-Endpoint Matrix (High Level)

- **Before pipeline**
  - `/documents/upload`, `/templates/upload`, template introspection endpoints
- **Pipeline start/control**
  - `/workflow-runs` (create + start)
- **In-flight visibility**
  - `/workflow-runs/{id}/status`
  - `/workflow-runs/{id}/events`
  - `/workflow-runs/{id}/observability`
- **Post-processing outputs**
  - `/outputs/{output_id}`
  - `/outputs/{output_id}/download`

---

## Notes on API Contracts

- All standard endpoints return a consistent success envelope via `success_response(...)`.
- Validation and domain failures are normalized by API error handlers.
- Correlation IDs are attached through request middleware (`X-Request-Id`).
