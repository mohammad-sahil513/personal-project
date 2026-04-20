# Ingestion Dependency Report

This report covers ingestion upstream triggers, file-level dependencies, downstream consumers, and operational side effects.

## Upstream Triggers

- Workflow-driven trigger
  - `backend/api/routes/workflow_routes.py` (`POST /workflow-runs` with `start_immediately`)
  - `backend/application/services/workflow_executor_service.py`
  - `backend/application/services/ingestion_runtime_bridge.py`

- Direct/manual trigger
  - `backend/scripts/run_ingestion.py`
  - `backend/manual_testing/run_ingestion_manual.py`
  - `backend/manual_testing/run_workflow_stagewise_manual.py`

## Core Files by Layer

### API / Application

- `backend/api/routes/workflow_routes.py`
- `backend/application/services/ingestion_runtime_bridge.py`
- `backend/application/services/ingestion_integration_service.py`
- `backend/application/services/ingestion_status_service.py`
- `backend/application/services/workflow_executor_service.py`
- `backend/application/dto/ingestion_dto.py`

### Ingestion Module

- Wiring and orchestration
  - `backend/modules/ingestion/live_wiring.py`
  - `backend/pipeline/bootstrap/ingestion_bootstrap.py`
  - `backend/pipeline/orchestrators/ingestion_orchestrator.py`

- Stage contracts
  - `backend/modules/ingestion/contracts/stage_1_contracts.py`
  - `backend/modules/ingestion/contracts/stage_2_contracts.py`
  - `backend/modules/ingestion/contracts/stage_3_contracts.py`
  - `backend/modules/ingestion/contracts/stage_4_contracts.py`
  - `backend/modules/ingestion/contracts/stage_5_contracts.py`
  - `backend/modules/ingestion/contracts/stage_6_contracts.py`
  - `backend/modules/ingestion/contracts/stage_7_contracts.py`
  - `backend/modules/ingestion/contracts/stage_8_contracts.py`
  - `backend/modules/ingestion/contracts/stage_9_contracts.py`

- Stage implementations
  - `backend/modules/ingestion/stages/01_upload_and_dedup.py`
  - `backend/modules/ingestion/stages/02_parse_document.py`
  - `backend/modules/ingestion/stages/03_mask_pii.py`
  - `backend/modules/ingestion/stages/04_classify_images.py`
  - `backend/modules/ingestion/stages/05_vision_extraction.py`
  - `backend/modules/ingestion/stages/06_segment_sections.py`
  - `backend/modules/ingestion/stages/07_validate_outputs.py`
  - `backend/modules/ingestion/stages/08_semantic_chunking.py`
  - `backend/modules/ingestion/stages/09_vector_indexing.py`

- Services and observability
  - `backend/modules/ingestion/services/*.py`
  - `backend/modules/ingestion/observability/*.py`
  - `backend/modules/ingestion/repositories/ingestion_repository.py`

## Stage Dependency Chain

- Stage output to input handoff is explicit and ordered:
  - Stage1 -> Stage2 -> Stage3 -> Stage4 -> Stage5 -> Stage6 -> Stage7 -> Stage8 -> Stage9
- Stage 9 is the retrieval-enabling boundary (index publication).

## Downstream Consumers

- Retrieval module reads ingestion-produced indexed chunks
  - `backend/modules/retrieval/repositories/search_repository.py`
  - `backend/modules/retrieval/services/vector_search_service.py`
  - `backend/modules/retrieval/contracts/index_contracts.py`

- Workflow status/UI surfaces ingestion progress
  - `backend/api/routes/workflow_routes.py` (`/status` ingestion block)
  - `frontend/src/pages/ProgressPage.tsx`
  - `frontend/src/store/useJobStore.ts`

## Data Contracts and Side Effects

- Bridge-required normalized fields:
  - `status`, `current_stage`, `completed_stages`, `total_stages`
- Ingestion artifacts and logs written under configured storage roots.
- Stage 9 writes search documents (including chunk fields and embeddings) to Azure AI Search.

## Storage and Artifact Paths (Operational)

- Local:
  - `backend/storage/documents`
  - `backend/storage/workflow_runs`
  - `backend/storage/executions`
  - `backend/storage/logs/ingestion_runs`

- Module job state:
  - `backend/storage/executions/ingestion/jobs/*.json`
  - `backend/storage/executions/ingestion/hash_registry.json`

## Frontend Dependencies on Ingestion Outcomes

- Upload and workflow creation:
  - `frontend/src/pages/UploadPage.tsx`
- Runtime polling and stage display:
  - `frontend/src/pages/ProgressPage.tsx`
  - `frontend/src/api/workflowApi.ts`
  - `frontend/src/api/types.ts`

## Test and Script Coverage

- Integration:
  - `backend/tests/integration/modules/ingestion/test_ingestion_pipeline.py`
- Unit:
  - `backend/tests/unit/modules/ingestion/*.py`
- Scripts/manual:
  - `backend/scripts/run_ingestion.py`
  - `backend/manual_testing/run_ingestion_manual.py`

## Practical Gaps Specific to Ingestion

- Document identity continuity requires careful handling between uploaded document IDs and ingestion-internal IDs.
- Duplicate/short-circuit flows can report completion without running full 2-9 stages.
- Some status semantics require checking validation payloads, not just stage status strings.
