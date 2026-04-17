## Pipeline Cheat Sheet

Detailed project mapping in the format:

`Phase -> Service Class -> Output Artifact`

---

## 0) Entry and Dispatch (Before Phase Execution)

- **API entry**
  - `backend/api/routes/workflow_routes.py`
  - Creates workflow metadata through `WorkflowService.create_workflow(...)`.
- **Execution orchestration**
  - `backend/application/services/workflow_executor_service.py`
  - Starts asynchronous execution via `TaskDispatcher`.
- **Background execution layer**
  - `backend/workers/task_dispatcher.py`
  - Dispatch mode priority:
    1. FastAPI `BackgroundTasks`
    2. `asyncio.create_task`
    3. `asyncio.run` fallback
- **Initial output artifacts**
  - Workflow metadata record (`workflow_run_id`, status, phase, progress).
  - Parent execution metadata record (`execution_id`, type `WORKFLOW`).

---

## 1) INPUT_PREPARATION

**Purpose:** Initialize workflow runtime state and prepare ingestion child execution.

- **Primary service class**
  - `WorkflowExecutorService` (`execute_workflow_skeleton`, `prepare_workflow_execution`)
- **Supporting service classes**
  - `ProgressService` (initializes phase structure)
  - `IngestionIntegrationService` (creates/finds ingestion execution)
  - `WorkflowService` (persists workflow state updates)
  - `WorkflowEventService` (publishes `workflow.started`)
- **Input**
  - `workflow_run_id`
- **Output artifacts**
  - Initialized `phases` array with weighted progress model.
  - `execution_refs.INGESTION` attached to workflow.
  - Ingestion child execution metadata created/reused.
  - Event stream message: `workflow.started`.

---

## 2) INGESTION

**Purpose:** Transform uploaded document into retrieval-ready indexed content.

- **Primary service class**
  - `IngestionRuntimeBridge` (`run_ingestion`)
- **Runtime wiring source**
  - `backend/modules/ingestion/live_wiring.py`
- **Workflow-side execution handler**
  - `WorkflowExecutorService._apply_ingestion_bridge_result(...)`
- **Ingestion sub-stage sequence (strict order)**
  1. `01_UPLOAD_AND_DEDUP`
  2. `02_PARSE_DOCUMENT`
  3. `03_MASK_PII`
  4. `04_CLASSIFY_IMAGES`
  5. `05_VISION_EXTRACTION`
  6. `06_SEGMENT_SECTIONS`
  7. `07_VALIDATE_OUTPUTS`
  8. `08_SEMANTIC_CHUNKING`
  9. `09_VECTOR_INDEXING`
- **Infra adapters involved**
  - Blob storage adapter
  - Document Intelligence adapter
  - OpenAI embedding client
  - Azure Search client adapter
- **Output artifacts**
  - Ingestion execution updates (`current_stage`, `completed_stages`, status).
  - Ingestion warnings/errors/artifacts.
  - Indexed vector/search documents.
  - Updated workflow phase/progress for ingestion.
  - Ingestion cost summary merged into workflow observability summary.

---

## 3) TEMPLATE_PREPARATION

**Purpose:** Ensure template context and compile-readiness for downstream generation.

- **Workflow progression owner**
  - `WorkflowExecutorService` phase movement logic
- **Related template lifecycle services**
  - `TemplateCompileService`
  - `TemplateRuntimeBridge`
  - `TemplateAppService`
- **Output artifacts**
  - Template-linked workflow context (`template_id` path ready).
  - Optional template compile status/artifacts (if compile path is triggered).
  - Workflow ready to proceed into section planning.

---

## 4) SECTION_PLANNING

**Purpose:** Build execution plan for sections and initialize section-level progress.

- **Primary service class**
  - `WorkflowExecutorService.build_and_attach_section_plan(...)`
- **Supporting service classes**
  - `SectionPlanningService` (builds `section_plan`)
  - `SectionProgressService` (builds initial `section_progress`)
  - `WorkflowService` (attaches plan/progress to workflow)
  - `WorkflowEventService` (publishes planning events)
- **Output artifacts**
  - `section_plan`:
    - section identifiers
    - titles
    - execution order
    - generation strategy
    - retrieval profile
    - dependencies
  - `section_progress`:
    - total/completed/running/failed section counters
  - Events:
    - `section.plan.attached`
    - `section.progress.initialized`

---

## 5) RETRIEVAL

**Purpose:** Retrieve evidence bundle for each planned section.

- **Primary service class**
  - `WorkflowSectionRetrievalService.run_retrieval_for_workflow(...)`
- **Supporting service classes**
  - `SectionRetrievalService` (per-section retrieval)
  - `WorkflowEventService` (started/completed/failed retrieval events)
- **Runtime wiring**
  - `backend/modules/retrieval/live_wiring.py`
  - Uses adapters from `backend/infrastructure/*`.
- **Per-section output artifact** (persisted in `section_retrieval_results`)
  - retrieval status/id
  - evidence bundle
  - confidence
  - diagnostics (including fallback/cost summary)
  - warnings/errors
- **Workflow-level output artifacts**
  - Full `section_retrieval_results` map attached to workflow.
  - Retrieval cost and diagnostics available to observability summary.

---

## 6) GENERATION

**Purpose:** Generate section outputs from section plan + retrieval evidence.

- **Primary service class**
  - `WorkflowExecutorService.run_section_generation(...)`
- **Supporting service classes**
  - `WorkflowSectionGenerationService`
  - `SectionGenerationService`
  - `SectionProgressService`
  - `WorkflowEventService`
- **Runtime wiring**
  - `backend/modules/generation/live_wiring.py`
- **Per-section output artifact**
  - `output_type` (text/table/diagram)
  - `content`
  - `artifacts`
  - diagnostics (model/validation/cost metadata)
  - warnings/errors
- **Workflow-level output artifacts**
  - `section_generation_results` map attached to workflow.
  - Section progress transitions (RUNNING/COMPLETED/FAILED).
  - Generation cost totals reflected in observability summary.

---

## 7) ASSEMBLY_VALIDATION

**Purpose:** Assemble ordered section outputs into one document structure.

- **Primary service class**
  - `WorkflowExecutorService.assemble_generated_sections(...)`
- **Supporting service class**
  - `DocumentAssemblyService.build_assembled_document(...)`
- **Validation guards**
  - `section_plan` must exist.
  - `section_generation_results` must exist.
  - Every planned section must have generation output.
- **Output artifact**
  - `assembled_document` attached to workflow:
    - title
    - ordered sections
    - section content
    - section metadata
- **Event**
  - `workflow.assembled`

---

## 8) RENDER_EXPORT

**Purpose:** Produce final exported document artifact and mark output ready.

- **Primary service classes**
  - `WorkflowExecutorService.prepare_output_export(...)`
  - `WorkflowExecutorService.render_and_finalize_output(...)`
- **Supporting service classes**
  - `OutputExportService`
  - `OutputService`
  - `DocxRendererService`
- **Two-step export lifecycle**
  1. **Prepare**
     - create output metadata (`output_id`, type `DOCUMENT`, format `DOCX`)
  2. **Render**
     - generate final DOCX at output path
     - mark output status ready with artifact path
- **Output artifacts**
  - Output metadata record.
  - Rendered `.docx` file.
  - Workflow updated with `output_id`.
  - Event message: `output.ready`.

---

## Cross-Cutting Persisted Artifacts

- **Workflow metadata**
  - status, phase, progress, execution refs, section plan/progress, retrieval/generation outputs, assembled document, observability summary.
- **Execution metadata**
  - parent execution (`WORKFLOW`)
  - child execution (`INGESTION`)
- **Document storage**
  - document metadata JSON
  - optional binary file
- **Output storage**
  - output metadata JSON
  - rendered DOCX artifact
- **Operational observability**
  - workflow event stream messages
  - ingestion logs/artifacts (when emitted by runtime)

---

## Fast Interview Summary (30 seconds)

Workflow creation is followed by async dispatch through `TaskDispatcher`. The execution proceeds through weighted phases: input preparation, a 9-step ingestion pipeline, template preparation, section planning, section retrieval, section generation, assembly, and final DOCX export. Each phase persists metadata, emits events, and contributes diagnostics/costs to observability, resulting in a fully traceable end-to-end pipeline.
