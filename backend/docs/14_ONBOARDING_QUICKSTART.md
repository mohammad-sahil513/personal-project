# 14 - Onboarding Quickstart

This quickstart gets a new developer from clone to first successful workflow run.

---

## 1) Prerequisites

- Python 3.11+ (recommended)
- Virtual environment tooling
- Access to required Azure services (if running full live flow)
- A `.env` file configured for local run

---

## 2) Environment Setup

From `backend/`:

```bash
python -m venv .venv
```

Activate:

- Windows PowerShell:
```bash
.\.venv\Scripts\Activate.ps1
```

Install dependencies (project-specific method used in your repo).

If using requirements:
```bash
pip install -r requirements.txt
```

---

## 3) Configure `.env`

Use `.env.example` as baseline and set:

- app and storage settings
- Azure OpenAI settings
- Azure Search settings
- Azure Blob settings
- Azure Document Intelligence settings

Minimum local checks:
- API prefix is valid
- storage root is writable
- required cloud keys/endpoints are set for live execution paths

---

## 4) Start the API

From project root (or backend root depending on your launch convention):

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Verify:

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/ready
```

---

## 5) First End-to-End Workflow Run

1. Upload a document:
   - `POST /api/v1/documents/upload`
2. Upload a template:
   - `POST /api/v1/templates/upload`
3. (Optional) compile template:
   - `POST /api/v1/templates/{template_id}/compile`
4. Create workflow:
   - `POST /api/v1/workflow-runs` with `start_immediately=true`
5. Track progress:
   - `GET /api/v1/workflow-runs/{id}/status`
   - `GET /api/v1/workflow-runs/{id}/events` (SSE)
6. After completion, fetch output:
   - `GET /api/v1/outputs/{output_id}`
   - `GET /api/v1/outputs/{output_id}/download`

Use `13_API_EXAMPLES.md` for ready cURL commands.

---

## 6) Useful Validation Scripts

From `backend/scripts/`:

- smoke:
  - `smoke_test.py`
- lifecycle:
  - `verify_lifecycle.py`
- endpoint checks:
  - `verify_endpoints.py`
- staging e2e:
  - `staging_workflow_e2e.py`

---

## 7) Troubleshooting Fast Path

If workflow is stuck:

1. Check `/status` endpoint for current phase.
2. Check `/events` stream for latest event.
3. Check `/observability` for stage costs and summaries.
4. Verify cloud env vars and service connectivity.

If output cannot download:

1. Confirm output status is `READY`.
2. Confirm artifact path exists.
3. Re-check export stage logs and renderer path.

---

## 8) Suggested First Week Learning Path

1. Read `01_PROJECT_OVERVIEW.md`
2. Read `02_FOLDER_GUIDE.md`
3. Read `05_STAGE_AND_API_REFERENCE.md`
4. Walk through `docs/diagrams/01` to `08`
5. Run one workflow and inspect all status/event endpoints
6. Run unit tests for one module area (ingestion/retrieval/generation/template)
