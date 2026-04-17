# Manual Stage Runners Guide (No pytest)

This guide documents the isolated manual testing toolkit in `backend/manual_testing`.

Goal:
- run each stage independently using your sample files
- inspect artifacts and intermediate stage snapshots
- keep outputs isolated from main runtime/test folders

This setup is manual verification only. It is not a unit test or pytest workflow.

## 1) What Is Included

Runners:
- `run_ingestion_manual.py`
- `run_template_preparation_manual.py`
- `run_section_planning_manual.py`
- `run_retrieval_manual.py`
- `run_generation_manual.py`
- `run_assembly_export_manual.py`
- `run_workflow_stagewise_manual.py` (full end-to-end, stage-by-stage capture)

Shared helper:
- `common.py` (run folder creation, logging, snapshots, polling, API response normalization)

## 2) Execution Modes

Every runner supports:
- `--mode local_services`
  - calls backend services directly inside Python
  - best for deep internal stage behavior visibility
  - no API server required
- `--mode local_api`
  - calls local HTTP endpoints (`/api/...`)
  - best for API-contract validation and near-real execution path
  - requires local backend server running

## 3) Environment and Prerequisites

Run commands from:
- `d:\ai-sdlc\backend`

Python environment:
```powershell
.\.venv\Scripts\python.exe --version
```

For `local_api` mode, start your backend app first (same machine), then use:
- `--base-url "http://127.0.0.1:8000"` (default)

Inputs you provide:
- sample document (`.pdf` preferred)
- sample template (`.docx`)

## 4) Standard CLI Contract

Common flags across runners:
- `--mode local_services|local_api`
- `--document "D:\path\input.pdf"` (required for most runners)
- `--template "D:\path\template.docx"` (required for template-based stages)
- `--output-root "manual_testing/output"` (default)
- `--base-url "http://127.0.0.1:8000"` (API mode)
- `--poll-interval-sec 5` (API polling interval)
- `--max-wait-sec 1800` (API stage timeout)

Tip:
- If you hit timeout due to heavy model/IO latency, increase:
  - `--max-wait-sec 3600`

## 5) Runner-by-Runner Detailed Usage

### A. Ingestion Only
Script: `run_ingestion_manual.py`

Purpose:
- validate ingestion input handling and ingestion-stage output snapshot

Inputs:
- required: `--document`

Outputs:
- stage folder: `stages/INGESTION/`
- files: `snapshot.json`, `stage_report.md`
- run metadata: document/workflow/execution references
- in local_services mode, metadata includes ingestion runtime logs root

Commands:
```powershell
.\.venv\Scripts\python.exe manual_testing\run_ingestion_manual.py --mode local_services --document "D:\samples\input.pdf"
```
```powershell
.\.venv\Scripts\python.exe manual_testing\run_ingestion_manual.py --mode local_api --document "D:\samples\input.pdf" --base-url "http://127.0.0.1:8000"
```

### B. Template Preparation / Compile
Script: `run_template_preparation_manual.py`

Purpose:
- verify template upload + compile state transitions

Inputs:
- required: `--template`

Outputs:
- stage folder: `stages/TEMPLATE_PREPARATION/`
- compile status snapshot and metadata

Commands:
```powershell
.\.venv\Scripts\python.exe manual_testing\run_template_preparation_manual.py --mode local_services --template "D:\samples\template.docx"
```
```powershell
.\.venv\Scripts\python.exe manual_testing\run_template_preparation_manual.py --mode local_api --template "D:\samples\template.docx"
```

### C. Section Planning
Script: `run_section_planning_manual.py`

Purpose:
- create prerequisites and capture section plan creation output

Inputs:
- required: `--document`
- required: `--template`

Outputs:
- stage folder: `stages/SECTION_PLANNING/`
- section plan payload captured in stage extra data

Commands:
```powershell
.\.venv\Scripts\python.exe manual_testing\run_section_planning_manual.py --mode local_services --document "D:\samples\input.pdf" --template "D:\samples\template.docx"
```
```powershell
.\.venv\Scripts\python.exe manual_testing\run_section_planning_manual.py --mode local_api --document "D:\samples\input.pdf" --template "D:\samples\template.docx"
```

### D. Retrieval
Script: `run_retrieval_manual.py`

Purpose:
- execute retrieval stage after section planning prerequisites

Inputs:
- required: `--document`
- required: `--template`

Outputs:
- stage folder: `stages/RETRIEVAL/`
- retrieval snapshot
- local_services mode: detailed `retrieval_results` in extra payload

Commands:
```powershell
.\.venv\Scripts\python.exe manual_testing\run_retrieval_manual.py --mode local_services --document "D:\samples\input.pdf" --template "D:\samples\template.docx"
```
```powershell
.\.venv\Scripts\python.exe manual_testing\run_retrieval_manual.py --mode local_api --document "D:\samples\input.pdf" --template "D:\samples\template.docx"
```

### E. Generation
Script: `run_generation_manual.py`

Purpose:
- execute generation stage after retrieval prerequisites

Inputs:
- required: `--document`
- required: `--template`

Outputs:
- stage folder: `stages/GENERATION/`
- workflow snapshot including section generation payload

Commands:
```powershell
.\.venv\Scripts\python.exe manual_testing\run_generation_manual.py --mode local_services --document "D:\samples\input.pdf" --template "D:\samples\template.docx"
```
```powershell
.\.venv\Scripts\python.exe manual_testing\run_generation_manual.py --mode local_api --document "D:\samples\input.pdf" --template "D:\samples\template.docx"
```

### F. Assembly + Export
Script: `run_assembly_export_manual.py`

Purpose:
- validate final document assembly and export stages

Inputs:
- required: `--document`
- required: `--template`

Outputs:
- stage folders:
  - `stages/ASSEMBLY_VALIDATION/`
  - `stages/RENDER_EXPORT/`
- output artifact:
  - `final_output.docx` (when produced)

Commands:
```powershell
.\.venv\Scripts\python.exe manual_testing\run_assembly_export_manual.py --mode local_services --document "D:\samples\input.pdf" --template "D:\samples\template.docx"
```
```powershell
.\.venv\Scripts\python.exe manual_testing\run_assembly_export_manual.py --mode local_api --document "D:\samples\input.pdf" --template "D:\samples\template.docx"
```

### G. Full Flow (Recommended for one-shot complete verification)
Script: `run_workflow_stagewise_manual.py`

Purpose:
- execute end-to-end workflow and capture all stage snapshots in one run

Inputs:
- required: `--document`
- required: `--template`

Outputs:
- stage snapshots across full flow
- `workflow_final_snapshot.json`
- `final_output.docx` if available

Commands:
```powershell
.\.venv\Scripts\python.exe manual_testing\run_workflow_stagewise_manual.py --mode local_services --document "D:\samples\input.pdf" --template "D:\samples\template.docx"
```
```powershell
.\.venv\Scripts\python.exe manual_testing\run_workflow_stagewise_manual.py --mode local_api --document "D:\samples\input.pdf" --template "D:\samples\template.docx"
```

## 6) Output Isolation and Folder Anatomy

All outputs remain isolated under:
- `manual_testing/output/<runner_name>/<run_id>/`

Expected files:
- `run_metadata.json`
  - high-level run context (mode, ids, source inputs, status)
- `events.log`
  - timestamped runner-level events for stage transitions
- `stages/<STAGE>/snapshot.json`
  - raw stage payload captured at that point
- `stages/<STAGE>/stage_report.md`
  - human-readable stage summary
- optional `stages/<STAGE>/extra.json`
  - stage-specific supplemental payload
- optional `workflow_final_snapshot.json`
- optional `final_output.docx`

## 7) Logging and Observability Expectations

Per-stage logging is present in all runners:
- runner-level timeline in `events.log`
- stage-level captured payload in `snapshot.json`
- stage summary in `stage_report.md`

Depth differences:
- `local_services`:
  - deeper service-side detail via direct runtime/service result payloads
  - ingestion metadata includes runtime logs path when available
- `local_api`:
  - detail level depends on API route response and exposed status payloads
  - useful for validating external API behavior and phase progression

## 8) Recommended Test Order

For first-time verification with new sample data:
1. `run_template_preparation_manual.py`
2. `run_ingestion_manual.py`
3. `run_section_planning_manual.py`
4. `run_retrieval_manual.py`
5. `run_generation_manual.py`
6. `run_assembly_export_manual.py`
7. `run_workflow_stagewise_manual.py` (complete consistency check)

## 9) Troubleshooting Playbook

If run fails:
- inspect `events.log` first for failing step
- inspect corresponding `stages/<STAGE>/snapshot.json`
- inspect `stages/<STAGE>/extra.json` when present
- confirm input file paths and extensions
- in `local_api` mode, confirm backend health route is reachable
- increase timeout for slow runs: `--max-wait-sec 3600`

If `final_output.docx` missing:
- check final stage snapshot for `output_id` and output status
- in API mode, verify output download endpoint response

If retrieval/generation payload seems thin:
- rerun using `--mode local_services` for deeper internal payloads

## 10) Notes on Stage Accuracy in API Mode

Some internal stage computations are not individually exposed as standalone API endpoints. In those cases, API-mode runners capture the nearest authoritative workflow phase snapshot. This keeps implementation minimal while preserving stage-wise manual verification and output isolation.
