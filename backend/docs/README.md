# Backend Documentation Hub

This folder is the central documentation hub for the backend project.

## Start Here

1. `01_PROJECT_OVERVIEW.md`
2. `02_FOLDER_GUIDE.md`
3. `05_STAGE_AND_API_REFERENCE.md`
4. `PIPELINE_PHASE_SERVICE_OUTPUT_CHEATSHEET.md`
5. `PROJECT_DIAGRAMS_MASTER_GUIDE.md`

## Full Documentation Index

### Core Project Docs
- `01_PROJECT_OVERVIEW.md` - Business purpose, architecture summary, and runtime model.
- `02_FOLDER_GUIDE.md` - Folder-by-folder ownership and boundaries.
- `03_FILE_CATALOG_CORE_API_APP.md` - File-level catalog for core, API, application, repositories, workers, and infrastructure.
- `04_FILE_CATALOG_MODULES.md` - File-level catalog for ingestion, retrieval, generation, template, observability, and pipeline modules.
- `05_STAGE_AND_API_REFERENCE.md` - Stage-by-stage pipeline plus API endpoint mapping.
- `06_DATA_STORAGE_AND_STATE.md` - Persistence model, state transitions, and artifact lifecycle.
- `07_OPERATIONS_AND_RUNBOOK.md` - Environment setup, run commands, verification, and troubleshooting.
- `08_CONNECTION_MAP.md` - Folder/service/stage connection map and API-stage linkage.
- `09_TESTS_DOCUMENTATION.md` - Test architecture and file-level test intent.
- `10_PROMPTS_DOCUMENTATION.md` - Prompt inventory and usage model.
- `11_SCRIPTS_AND_UTILITIES.md` - Script catalog and operational use guidance.
- `12_CONFIG_AND_PRICING_REFERENCE.md` - Static config assets and runtime config reference.
- `13_API_EXAMPLES.md` - Practical cURL request/response examples.
- `14_ONBOARDING_QUICKSTART.md` - Setup-to-first-workflow onboarding path.
- `15_CONTRIBUTION_GUIDE.md` - Contribution workflow, standards, and checklist.

### Pipeline and Diagram Docs
- `PIPELINE_PHASE_SERVICE_OUTPUT_CHEATSHEET.md` - Detailed phase -> service -> output mapping.
- `PROJECT_DIAGRAMS_MASTER_GUIDE.md` - Full diagram strategy and templates.
- `diagrams/` - Concrete architecture and flow diagrams (`01` to `16`).

### Dependency and Gap Reports
- `GAPS_AND_MISMATCHES_REPORT.md` - Practical gaps and known risks/mismatches summary.
- `dependency-reports/README.md` - Index for detailed upstream/downstream dependency reports.
- `dependency-reports/00_SYSTEM_DEPENDENCY_OVERVIEW.md` - Cross-module system dependency map.
- `dependency-reports/01_INGESTION_DEPENDENCY_REPORT.md` - Ingestion-centric dependency and artifact report.
- `dependency-reports/02_TEMPLATE_PLANNING_RETRIEVAL_REPORT.md` - Template, planning, and retrieval dependency report.
- `dependency-reports/03_GENERATION_ASSEMBLY_EXPORT_REPORT.md` - Generation, assembly, and export dependency report.
- `dependency-reports/04_PRACTICAL_GAPS_AND_RISKS_APPENDIX.md` - Consolidated practical gaps, mismatches, and actions.

## Scope Note

The file catalogs in this documentation focus on project source/runtime areas.
They intentionally exclude dependency/vendor paths such as `.venv`, and runtime
generated data folders such as `storage` snapshots.

## Recent API / UX Updates

- Template preview in frontend now renders the actual uploaded DOCX in a popup modal.
- A supporting endpoint is available for template binary download:
  - `GET /api/templates/{template_id}/download`
- Template selection on upload flow is now library-only (templates are uploaded via `/templates` page).
- Local CORS defaults include both `localhost` and `127.0.0.1` for ports `3000` and `5173`.
