# 11 - Scripts and Utilities Documentation

This document catalogs utility scripts in `backend/scripts` and their purpose.

## Script Categories

## End-to-End and lifecycle checks
- `scripts/smoke_test.py` - high-level smoke verification.
- `scripts/staging_workflow_e2e.py` - staging-focused workflow end-to-end run.
- `scripts/run_mock_e2e_integration.py` - mock-driven integration flow.
- `scripts/verify_lifecycle.py` - workflow lifecycle verification utility.
- `scripts/verify_endpoints.py` - endpoint reachability/contract verification helper.

## Phase-specific validation
- `scripts/test_phase1.py` - phase 1 checks.
- `scripts/test_phase2_template_bridge.py` - template bridge phase checks.
- `scripts/test_phase3_retrieval_generation_bridge.py` - retrieval/generation bridge checks.
- `scripts/test_phase4_rendering.py` - rendering/export phase checks.

## Ingestion and retrieval tooling
- `scripts/run_ingestion.py` - run ingestion workflow path manually.
- `scripts/run_retrieval_integration.py` - run retrieval integration utility.
- `scripts/retrieval_live_smoke.py` - live retrieval smoke checks.

## Template/Docx utility scripts
- `scripts/test_docx_structure_extraction.py` - DOCX structure extraction validation.
- `scripts/rebuild_docx_from_extraction.py` - rebuild DOCX from extracted structure.
- `scripts/generate_placeholder_docx.py` - generate placeholder DOCX for testing.
- `scripts/run_template_azure_smoke.py` - template cloud integration smoke.

## Platform and cleanup scripts
- `scripts/create_ai_search_index.py` - create/configure search index.
- `scripts/cleanup_blob_test_artifacts.py` - cleanup test artifacts from blob storage.

## Safe Usage Guidance

- Use scripts in non-production first unless explicitly designed for production.
- Validate environment variables before cloud-dependent scripts.
- Prefer idempotent behavior for provisioning/cleanup utilities.
- Record script output/logs when using them for release validation evidence.

## Recommended Script Workflow

1. Local smoke (`smoke_test.py`)
2. Targeted phase verification scripts
3. Integration scripts (`run_*_integration.py`)
4. Staging E2E (`staging_workflow_e2e.py`)
