# 04 - File Catalog (Modules and Pipeline)

This catalog documents module internals where most domain logic resides.

## `modules/ingestion/`

### Wiring and orchestration support
- `modules/ingestion/live_wiring.py`
- `modules/ingestion/exceptions.py`

### Contracts (`contracts/`)
- `stage_1_contracts.py`
- `stage_2_contracts.py`
- `stage_3_contracts.py`
- `stage_4_contracts.py`
- `stage_5_contracts.py`
- `stage_6_contracts.py`
- `stage_7_contracts.py`
- `stage_8_contracts.py`
- `stage_9_contracts.py`

### Stages (`stages/`)
- `01_upload_and_dedup.py`
- `02_parse_document.py`
- `03_mask_pii.py`
- `04_classify_images.py`
- `05_vision_extraction.py`
- `06_segment_sections.py`
- `07_validate_outputs.py`
- `08_semantic_chunking.py`
- `09_vector_indexing.py`

### Services (`services/`)
- `upload_service.py`
- `parser_service.py`
- `pii_service.py`
- `pii_classifier_adapter.py`
- `image_classification_service.py`
- `vision_extraction_service.py`
- `segmentation_service.py`
- `validation_service.py`
- `chunking_service.py`
- `indexing_service.py`
- `asset_extraction_service.py`
- `table_extraction_service.py`
- `hyperlink_extraction_service.py`
- `cleanup_service.py`

### Repository
- `repositories/ingestion_repository.py`

### Observability (`observability/`)
- `observer.py`
- `observed_runners.py`
- `loggers.py`
- `models.py`
- `artifact_store.py`

## `modules/retrieval/`

### Wiring
- `modules/retrieval/live_wiring.py`

### Contracts (`contracts/`)
- `retrieval_contracts.py`
- `evidence_contracts.py`
- `index_contracts.py`

### Profiles
- `profiles/retrieval_profiles.py`

### Repository
- `repositories/search_repository.py`

### Services (`services/`)
- `retrieval_service.py`
- `vector_search_service.py`
- `reranker_service.py`
- `query_builder.py`
- `evidence_packager.py`
- `profile_resolver.py`
- `fallback_service.py`

## `modules/generation/`

### Wiring
- `modules/generation/live_wiring.py`

### Contracts (`contracts/`)
- `generation_contracts.py`
- `session_contracts.py`

### Models
- `models/generation_config.py`

### Orchestrators (`orchestrators/`)
- `generation_orchestrator.py`
- `section_executor.py`
- `wave_executor.py`
- `dependency_checker.py`

### Generators (`generators/`)
- `text_generator.py`
- `table_generator.py`
- `test_table_generator.py`
- `diagram_generator.py`
- `prompt_assembler.py`

### Diagram helpers (`diagram/`)
- `kroki_client.py`
- `plantuml_normalizer.py`
- `plantuml_validator.py`
- `repair_loop.py`
- `diagram_artifact_store.py`
- `diagram_embedder.py`

### Validation and streaming
- `validators/output_validator.py`
- `validators/correction_loop.py`
- `streaming/sse_publisher.py`

### Assembly helpers (`assembly/`)
- `section_assembler.py`
- `toc_generator.py`
- `layout_normalizer.py`

## `modules/template/`

### Wiring
- `modules/template/live_wiring.py`

### Contracts (`contracts/`)
- `template_contracts.py`
- `section_contracts.py`
- `validation_contracts.py`
- `compiler_contracts.py`

### Models
- `models/template_config.py`
- `models/template_enums.py`

### Repository
- `repositories/template_repository.py`

### Services (`services/`)
- `template_loader_service.py`
- `template_validator_service.py`
- `template_resolver_service.py`
- `template_artifact_service.py`
- `prompt_selector_service.py`
- `dependency_sorter_service.py`
- `template_blob_publisher_service.py`

### Compiler (`compiler/`)
- `compiler_orchestrator.py`
- `ai_compiler.py`
- `azure_sk_structured_adapter.py`
- `semantic_validator.py`
- `heuristic_mapper.py`
- `docx_extractor.py`
- `header_normalizer.py`
- `defaults_injector.py`
- `correction_loop.py`
- `template_blob_publisher_service.py`

### Layout (`layout/`)
- `layout_extractor.py`
- `layout_contracts.py`
- `shell_builder.py`
- `style_parser.py`
- `table_format_parser.py`
- `page_setup_parser.py`
- `header_footer_parser.py`

## `modules/observability/`

### Services
- `services/logging_service.py`
- `services/request_context_service.py`
- `services/pricing_registry_service.py`
- `services/cost_estimator_service.py`
- `services/cost_aggregation_service.py`

## `pipeline/`

### Orchestrator
- `pipeline/orchestrators/ingestion_orchestrator.py`

### Planners
- `pipeline/planners/progress_planner.py`
- `pipeline/planners/section_execution_planner.py`
- `pipeline/planners/__init__.py`

### Bootstrap
- `pipeline/bootstrap/ingestion_bootstrap.py`

### Package markers
- `pipeline/__init__.py`

---

## How to Read Module Ownership

- `contracts/` define typed boundaries and payload shapes.
- `services/` implement business behavior.
- `repositories/` isolate data access for module needs.
- `live_wiring.py` composes concrete runtime dependencies.
- `orchestrators/` coordinate multi-step operations within the module.
