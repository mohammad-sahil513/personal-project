# System Dependency Overview

This report maps major modules and dependency paths across backend and frontend for the workflow lifecycle.

## End-to-End Flow (High Level)

1. Document upload (`/documents/upload`)
2. Template upload/select (`/templates/*`)
3. Workflow creation/start (`/workflow-runs`)
4. Ingestion runtime
5. Template preparation and section planning
6. Retrieval per section
7. Generation per section
8. Assembly and export
9. Output download (`/outputs/{output_id}/download`)

## Backend Dependency Spine

- API entry and routing
  - `backend/main.py`
  - `backend/api/router.py`
  - `backend/api/routes/*.py`

- Workflow orchestration and state
  - `backend/application/services/workflow_executor_service.py`
  - `backend/application/services/workflow_service.py`
  - `backend/application/services/workflow_event_service.py`

- Module bridges and runtimes
  - Ingestion: `backend/application/services/ingestion_runtime_bridge.py`
  - Template: `backend/application/services/template_runtime_bridge.py`
  - Retrieval: `backend/application/services/retrieval_runtime_bridge.py`
  - Generation: `backend/application/services/generation_runtime_bridge.py`

- Planning and progress
  - `backend/application/services/section_planning_service.py`
  - `backend/application/services/section_progress_service.py`
  - `backend/pipeline/planners/section_execution_planner.py`
  - `backend/pipeline/planners/progress_planner.py`

## Frontend Dependency Spine

- Route-level orchestration
  - `frontend/src/pages/UploadPage.tsx`
  - `frontend/src/pages/ProgressPage.tsx`
  - `frontend/src/pages/OutputPage.tsx`

- API clients and contracts
  - `frontend/src/api/client.ts`
  - `frontend/src/api/documentApi.ts`
  - `frontend/src/api/templateApi.ts`
  - `frontend/src/api/workflowApi.ts`
  - `frontend/src/api/outputApi.ts`
  - `frontend/src/api/types.ts`

- Runtime state container
  - `frontend/src/store/useJobStore.ts`

## Persistence and Artifact Surfaces

- Primary storage roots (configured)
  - `backend/storage/workflow_runs`
  - `backend/storage/documents`
  - `backend/storage/templates`
  - `backend/storage/outputs`
  - `backend/storage/executions`
  - `backend/storage/logs`

- Repository owners
  - `backend/repositories/workflow_repository.py`
  - `backend/repositories/document_repository.py`
  - `backend/repositories/template_metadata_repository.py`
  - `backend/repositories/output_repository.py`
  - `backend/repositories/execution_repository.py`

## Shared Contract Anchors

- API envelope: `backend/core/response.py`
- Workflow aggregate DTO: `backend/application/dto/workflow_dto.py`
- Section plan DTO: `backend/application/dto/section_plan_dto.py`
- Retrieval DTO: `backend/application/dto/retrieval_dto.py`
- Generation DTO: `backend/application/dto/generation_dto.py`
- Assembled document DTO: `backend/application/dto/assembled_document_dto.py`
- Output DTO: `backend/application/dto/output_dto.py`

## Important Integration Constraints

- Frontend defaults to `/api`; backend prefix defaults to `/api`.
- Frontend assumes successful workflow eventually exposes:
  - `status = COMPLETED`
  - `assembled_document.sections`
  - `output_id`
- Workflow events are available via SSE endpoints, but frontend currently uses polling-based status updates.
