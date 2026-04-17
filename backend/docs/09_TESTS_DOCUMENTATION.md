# 09 - Tests Documentation

This document explains the test layout and what each test area validates.

## Test Structure

- `tests/unit/` - Isolated behavior tests for functions/classes/modules.
- `tests/integration/` - Cross-module and API flow tests.
- `tests/conftest.py` - Shared fixtures and test setup utilities.

## Unit Test Areas

## Core
- `tests/unit/core/test_config.py` - settings parsing and defaults.
- `tests/unit/core/test_constants.py` - constant integrity.
- `tests/unit/core/test_exceptions.py` - custom exception behavior.
- `tests/unit/core/test_ids.py` - ID generation helpers.
- `tests/unit/core/test_logging.py` - logger setup behavior.
- `tests/unit/core/test_request_context.py` - request ID context behavior.
- `tests/unit/core/test_response.py` - response envelope formatting.

## API
- `tests/unit/api/test_api_layer.py` - API layer behavior/contracts.

## Application
- `tests/unit/application/dto/test_dtos.py` - DTO validation/serialization.
- `tests/unit/application/services/test_app_services.py` - core application services.
- `tests/unit/application/services/test_workflow_section_retrieval_service.py` - workflow retrieval orchestration.

## Repositories
- `tests/unit/repositories/test_document_repository.py`
- `tests/unit/repositories/test_template_metadata_repository.py`
- `tests/unit/repositories/test_workflow_repository.py`
- `tests/unit/repositories/test_execution_repository.py`
- `tests/unit/repositories/test_output_repository.py`

## Workers
- `tests/unit/workers/test_background_runner.py`
- `tests/unit/workers/test_task_dispatcher.py`

## Pipeline Planners
- `tests/unit/pipeline/test_progress_planner.py`
- `tests/unit/pipeline/test_section_execution_planner.py`

## Module Tests

### Ingestion
- `tests/unit/modules/ingestion/test_upload_service.py`
- `tests/unit/modules/ingestion/test_parser_service.py`
- `tests/unit/modules/ingestion/test_pii_service.py`
- `tests/unit/modules/ingestion/test_segmentation_service.py`
- `tests/unit/modules/ingestion/test_validation_service.py`
- `tests/unit/modules/ingestion/test_chunking_service.py`
- `tests/unit/modules/ingestion/test_ingestion_repository.py`
- `tests/unit/modules/ingestion/test_ingestion_contracts.py`

### Retrieval
- `tests/unit/modules/retrieval/test_query_builder.py`
- `tests/unit/modules/retrieval/test_vector_search_service.py`
- `tests/unit/modules/retrieval/test_reranker_service.py`
- `tests/unit/modules/retrieval/test_evidence_packager.py`
- `tests/unit/modules/retrieval/test_retrieval_contracts.py`

### Generation
- `tests/unit/modules/generation/test_generation_contracts.py`
- `tests/unit/modules/generation/test_generators.py`
- `tests/unit/modules/generation/test_output_validator.py`
- `tests/unit/modules/generation/test_assembly.py`

### Template
- `tests/unit/modules/template/test_template_models.py`
- `tests/unit/modules/template/test_template_contracts.py`
- `tests/unit/modules/template/test_template_loader_service.py`
- `tests/unit/modules/template/test_template_resolver_service.py`
- `tests/unit/modules/template/test_template_validator_service.py`
- `tests/unit/modules/template/test_dependency_sorter_service.py`
- `tests/unit/modules/template/test_template_repository.py`
- `tests/unit/modules/template/test_compiler/test_docx_extractor.py`
- `tests/unit/modules/template/test_compiler/test_header_normalizer.py`
- `tests/unit/modules/template/test_compiler/test_defaults_injector.py`
- `tests/unit/modules/template/test_compiler/test_heuristic_mapper.py`
- `tests/unit/modules/template/test_compiler/test_semantic_validator.py`

### Observability
- `tests/unit/modules/observability/test_observability.py`

## Integration Test Areas

- `tests/integration/test_api_endpoints.py` - broad API endpoint integration.
- `tests/integration/test_workflow_lifecycle.py` - full workflow lifecycle path.
- `tests/integration/test_template_to_workflow.py` - template-to-workflow integration.
- `tests/integration/modules/ingestion/test_ingestion_pipeline.py` - ingestion pipeline integration.
- `tests/integration/modules/retrieval/test_retrieval_pipeline.py` - retrieval integration path.
- `tests/integration/modules/generation/test_generation_pipeline.py` - generation integration path.

## Coverage Intent

The test suite is organized to validate:

- contract correctness (DTO/contracts/schemas)
- deterministic service behavior
- stage orchestration correctness
- API behavior consistency
- module-level integration readiness

## Suggested Test Execution Layers

1. Fast checks: unit only.
2. Pre-merge checks: unit + targeted integration.
3. Release checks: full integration suite + smoke scripts.
