# 06 - Data Storage and State Model

## Persistence Surfaces

The backend persists data across multiple logical surfaces:

1. **Workflow metadata**
2. **Execution metadata** (parent workflow + child ingestion)
3. **Document metadata and binaries**
4. **Template metadata and compile artifacts**
5. **Output metadata and rendered files**
6. **Ingestion run logs and artifacts**
7. **Cloud retrieval index data**

## Local Storage Paths (Configured)

Derived from `core/config.py`:

- `storage_root_path`
- `workflow_runs_path`
- `documents_path`
- `templates_path`
- `outputs_path`
- `executions_path`
- `logs_path`

## Core Record Types

## Workflow record
- Key: `workflow_run_id`
- Stores:
  - status/current phase/progress
  - execution refs
  - section plan and section progress
  - retrieval/generation results
  - assembled document reference data
  - output link and observability summary

## Execution record
- Key: `execution_id`
- Types:
  - `WORKFLOW`
  - `INGESTION`
- Stores:
  - status
  - stage progression metadata
  - warnings/errors/artifacts

## Document record
- Key: `document_id`
- Stores metadata and optional `.bin` payload.

## Output record
- Key: `output_id`
- Stores format/status/artifact path and workflow linkage.

---

## State Machines

## Workflow status
- `PENDING -> RUNNING -> COMPLETED`
- `PENDING/RUNNING -> FAILED` on unrecoverable path

## Ingestion execution status
- `PENDING -> RUNNING -> COMPLETED`
- `RUNNING -> FAILED`

## Section progress (within workflow)
- per-section states transition through pending/running/completed/failed.
- aggregate section progress updates workflow overall progress.

---

## Data Lifecycle Summary

1. Document uploaded.
2. Document parsed and transformed during ingestion.
3. Chunks generated and indexed.
4. Retrieval evidence generated per section.
5. Generation output produced per section.
6. Sections assembled into final document structure.
7. DOCX rendered and output marked `READY`.

---

## Observability-Coupled State

Observability summary is computed from:

- ingestion stage logs/cost metadata
- retrieval diagnostics/cost summaries
- generation diagnostics/cost estimates

This summary is attached to workflow metadata and exposed via observability APIs.
