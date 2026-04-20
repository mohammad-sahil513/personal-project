# Template, Planning, and Retrieval Dependency Report

This report maps dependencies for template preparation, section planning, and retrieval execution.

## Upstream Dependencies

- Template metadata and binary must exist before planning:
  - `backend/api/routes/template_routes.py`
  - `backend/application/services/template_app_service.py`
  - `backend/repositories/template_metadata_repository.py`

- Workflow context drives planning and retrieval:
  - `backend/api/routes/workflow_routes.py`
  - `backend/application/services/workflow_service.py`
  - `backend/application/services/workflow_executor_service.py`

- Ingestion index output is required for retrieval relevance:
  - `backend/modules/ingestion/stages/09_vector_indexing.py`
  - `backend/modules/retrieval/repositories/search_repository.py`

## Core Files by Capability

### Template Preparation and Resolution

- `backend/application/services/template_compile_service.py`
- `backend/application/services/template_introspection_service.py`
- `backend/application/services/template_runtime_bridge.py`
- `backend/application/services/template_resolve_bridge.py`
- `backend/application/services/template_validation_bridge.py`
- `backend/modules/template/live_wiring.py`
- `backend/modules/template/services/template_artifact_service.py`
- `backend/modules/template/repositories/template_repository.py`
- `backend/modules/template/contracts/*.py`

### Section Planning

- `backend/application/services/section_planning_service.py`
- `backend/application/services/section_progress_service.py`
- `backend/pipeline/planners/section_execution_planner.py`
- `backend/pipeline/planners/progress_planner.py`
- `backend/application/dto/section_plan_dto.py`

### Retrieval Runtime

- `backend/application/services/workflow_section_retrieval_service.py`
- `backend/application/services/section_retrieval_service.py`
- `backend/application/services/retrieval_runtime_bridge.py`
- `backend/modules/retrieval/live_wiring.py`
- `backend/modules/retrieval/services/retrieval_service.py`
- `backend/modules/retrieval/services/query_builder.py`
- `backend/modules/retrieval/services/vector_search_service.py`
- `backend/modules/retrieval/services/reranker_service.py`
- `backend/modules/retrieval/services/evidence_packager.py`
- `backend/modules/retrieval/contracts/*.py`
- `backend/modules/retrieval/profiles/retrieval_profiles.py`

## Downstream Effects

- Planning output (`section_plan`) feeds:
  - retrieval profile selection
  - generation strategy routing
  - section dependency ordering

- Retrieval output (`section_retrieval_results`) feeds:
  - generation per section
  - diagnostics and observability rollups

- Workflow DTO gets enriched with:
  - `section_plan`
  - `section_progress`
  - `section_retrieval_results`

## APIs and Frontend Consumers

- Backend endpoints:
  - Template endpoints: `/templates/*`
  - Workflow endpoints: `/workflow-runs`, `/workflow-runs/{id}`, `/status`, `/sections`, `/observability`

- Frontend consumers:
  - `frontend/src/api/templateApi.ts`
  - `frontend/src/api/workflowApi.ts`
  - `frontend/src/pages/UploadPage.tsx`
  - `frontend/src/pages/ProgressPage.tsx`

- Current frontend usage pattern:
  - relies heavily on workflow status polling
  - does not consume template compile/resolve/validate APIs directly in the main run path

## Contracts and Artifacts

- Planning contract:
  - `SectionPlanDTO`, `SectionPlanItemDTO`
- Retrieval app contract:
  - `RetrievalResultDTO`
- Retrieval module contracts:
  - retrieval plan/request/diagnostics and evidence models in `backend/modules/retrieval/contracts`
- Template compile artifacts:
  - compiled template definition and optional manifest/shell artifacts

## Storage and Repositories

- Template metadata and binaries:
  - `backend/storage/templates`
- Workflow and execution records:
  - `backend/storage/workflow_runs`
  - `backend/storage/executions`
- Retrieval index backend:
  - Azure AI Search via `backend/infrastructure/search/search_client.py`

## Test and Script Coverage

- Integration:
  - `backend/tests/integration/test_template_to_workflow.py`
  - `backend/tests/integration/modules/retrieval/test_retrieval_pipeline.py`
- Unit:
  - `backend/tests/unit/modules/template/*.py`
  - `backend/tests/unit/modules/retrieval/*.py`
  - `backend/tests/unit/pipeline/test_section_execution_planner.py`
- Manual/scripts:
  - `backend/manual_testing/run_template_preparation_manual.py`
  - `backend/manual_testing/run_section_planning_manual.py`
  - `backend/manual_testing/run_retrieval_manual.py`
  - `backend/scripts/test_phase2_template_bridge.py`
  - `backend/scripts/test_phase3_retrieval_generation_bridge.py`

## Practical Gaps for This Segment

- API-triggered workflow path does not always chain planning/retrieval automatically after ingestion.
- Template artifact expectations (manifest/shell) can diverge from runtime compile outputs.
- Phase/event naming and casing are not fully standardized across all producers.
