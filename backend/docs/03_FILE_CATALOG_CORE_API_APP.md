# 03 - File Catalog (Core, API, Application, Repositories, Workers, Infrastructure)

This catalog documents source files and their intent for the foundational layers.

## `core/`

- `core/config.py` - Settings model and cached configuration loader.
- `core/constants.py` - Central defaults and constant values.
- `core/exceptions.py` - Domain and API-safe error classes.
- `core/ids.py` - Identifier generation helpers.
- `core/logging.py` - Logger configuration and access helpers.
- `core/request_context.py` - Request ID lifecycle/context management.
- `core/response.py` - Standard success response envelope helper.
- `core/__init__.py` - Package marker.

## `api/`

### Root API files
- `api/router.py` - Root API router wiring and route inclusion.
- `api/dependencies.py` - Shared dependency providers (logger, settings, workflow event broker).
- `api/error_handlers.py` - Exception to HTTP mapping and unified error responses.
- `api/__init__.py` - Package marker.

### Schemas
- `api/schemas/common.py` - Shared response/payload schema fragments.
- `api/schemas/document.py` - Document API request/response schemas.
- `api/schemas/template.py` - Template API payload schemas.
- `api/schemas/workflow.py` - Workflow API request schemas.
- `api/schemas/workflow_inspection.py` - Workflow inspection schemas.
- `api/schemas/__init__.py` - Package marker.

### Routes
- `api/routes/health_routes.py` - Liveness and readiness endpoints.
- `api/routes/document_routes.py` - Document upload/list/get/delete endpoints.
- `api/routes/template_routes.py` - Template upload, compile, validate, resolve, artifact download endpoints.
- `api/routes/workflow_routes.py` - Workflow create/list/get/status/sections/observability endpoints.
- `api/routes/workflow_event_routes.py` - Workflow SSE event stream endpoint.
- `api/routes/workflow_inspection_routes.py` - Errors/artifacts/events snapshot/diagnostics endpoints.
- `api/routes/output_routes.py` - Output metadata and file download endpoints.
- `api/routes/generation_routes.py` - Generation job start/status/SSE endpoints.
- `api/routes/__init__.py` - Package marker.

## `application/dto/`

- `application/dto/document_dto.py` - Document metadata DTO.
- `application/dto/template_dto.py` - Template DTO and compile fields.
- `application/dto/workflow_dto.py` - Workflow aggregate DTO.
- `application/dto/ingestion_dto.py` - Ingestion execution DTO.
- `application/dto/retrieval_dto.py` - Retrieval result DTOs.
- `application/dto/generation_dto.py` - Generation result DTOs.
- `application/dto/assembled_document_dto.py` - Assembled document DTO.
- `application/dto/output_dto.py` - Output artifact metadata DTO.
- `application/dto/section_plan_dto.py` - Section planning DTOs.
- `application/dto/section_progress_dto.py` - Section progress DTOs.
- `application/dto/workflow_event_dto.py` - Workflow event payload DTO.
- `application/dto/__init__.py` - Package marker.

## `application/services/`

### Workflow lifecycle
- `application/services/workflow_service.py` - CRUD + workflow field attachments and status updates.
- `application/services/workflow_executor_service.py` - End-to-end workflow shell orchestration and failure handling.
- `application/services/progress_service.py` - Workflow phase progress operations.
- `application/services/section_planning_service.py` - Build section plan from template.
- `application/services/section_progress_service.py` - Section-level state transitions and percentage rollups.
- `application/services/workflow_event_service.py` - Event publish/stream broker abstraction.
- `application/services/workflow_inspection_service.py` - Read inspection-friendly workflow diagnostics.

### Ingestion integration
- `application/services/ingestion_integration_service.py` - Child ingestion execution metadata management.
- `application/services/ingestion_status_service.py` - User-facing ingestion status/step text mapping.
- `application/services/ingestion_runtime_bridge.py` - Bridge to live ingestion runtime with normalization.
- `application/services/ingestion_orchestrator_adapter.py` - Adapter glue for ingestion orchestration shape.

### Retrieval + generation integration
- `application/services/section_retrieval_service.py` - Single-section retrieval use-case.
- `application/services/workflow_section_retrieval_service.py` - Workflow-wide retrieval loop + events.
- `application/services/retrieval_runtime_bridge.py` - Bridge to retrieval runtime.
- `application/services/section_generation_service.py` - Single-section generation use-case.
- `application/services/workflow_section_generation_service.py` - Workflow-wide generation loop.
- `application/services/generation_runtime_bridge.py` - Bridge to generation runtime.

### Template lifecycle
- `application/services/template_app_service.py` - Template metadata CRUD + status updates.
- `application/services/template_compile_service.py` - Compile dispatch and compile status transitions.
- `application/services/template_runtime_bridge.py` - Bridge to template compile runtime.
- `application/services/template_validation_bridge.py` - Bridge for template validation.
- `application/services/template_resolve_bridge.py` - Bridge for template resolution.
- `application/services/template_introspection_service.py` - Unified validate/resolve/compiled view service.
- `application/services/template_artifact_service.py` - Manifest/shell artifact access service.

### Document and output lifecycle
- `application/services/document_service.py` - Document metadata + binary management.
- `application/services/document_assembly_service.py` - Ordered section assembly into final document structure.
- `application/services/output_service.py` - Output metadata CRUD and readiness transitions.
- `application/services/output_export_service.py` - Export preparation and DOCX export flow.
- `application/services/docx_renderer_service.py` - DOCX rendering helper.
- `application/services/__init__.py` - Package marker.

## `repositories/`

- `repositories/document_repository.py` - Document metadata + binary file persistence.
- `repositories/template_metadata_repository.py` - Template metadata persistence.
- `repositories/workflow_repository.py` - Workflow record persistence.
- `repositories/execution_repository.py` - Execution record persistence.
- `repositories/output_repository.py` - Output record persistence.
- `repositories/__init__.py` - Package marker.

## `workers/`

- `workers/task_dispatcher.py` - Background dispatch strategy with error callback handling.
- `workers/background_runner.py` - Unified callable runner for sync/async functions.
- `workers/__init__.py` - Worker package marker and intent.

## `infrastructure/`

- `infrastructure/ai_clients/openai_client.py` - Azure OpenAI embedding adapter.
- `infrastructure/ai_clients/sk_unified_adapter.py` - Semantic Kernel unified Azure text adapter.
- `infrastructure/search/search_client.py` - Azure AI Search query adapter.

## Entrypoint

- `main.py` - FastAPI app bootstrap, middleware, CORS, route registration, lifecycle hooks.

---

## Notes

- This catalog focuses on source/runtime files.
- Test files are documented by behavior through test suites and are not enumerated here.
