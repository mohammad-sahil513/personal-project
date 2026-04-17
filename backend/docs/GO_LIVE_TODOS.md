# Go-live checklist (your decisions applied)

**Auth:** Not required for your deployment — no API key / OAuth work items below.

---

## 1. `generation_routes` — do you need to add it?

**Recommendation: no, unless you need a standalone “generation job” HTTP API.**

| Fact | Detail |
|------|--------|
| **What it would add** | `POST /api/.../generate-document`, status, and SSE for **job-based** generation (separate from workflow runs). |
| **Current product path** | Document → template → **workflow** (`/api/workflow-runs`) already runs section generation via `WorkflowSectionGenerationService`. |
| **Blocker if you mount it today** | Dependencies `get_generation_route_service` and `get_sse_publisher` in [`api/routes/generation_routes.py`](../api/routes/generation_routes.py) **raise `NotImplementedError`** — wiring is unfinished. |
| **Path quirk** | Routes are declared as `/api/generate-document/...`; the app already prefixes routers with `/api`, so mounting as-is can produce **`/api/api/...`** unless paths are fixed to `/generate-document/...`. |

**Your todo:**

- [ ] **If you only need workflow-based generation:** leave `generation_routes` **unmounted** (current [`api/router.py`](../api/router.py)); no action.
- [ ] **If you need standalone generation API:** (1) implement `GenerationRouteService` + SSE publisher overrides in dependencies, (2) include the router in `api_router`, (3) fix path prefixes to avoid `/api/api/...`.

---

## 2. Staging E2E against real Azure

**Automated connectivity check (run in staging with real secrets):**

1. Copy [`../.env.example`](../.env.example) to **`backend/.env`** (or repo root `.env` — `load_dotenv()` loads from CWD).
2. Fill all Azure variables (OpenAI, Document Intelligence, Search, Blob, container name, root prefix).
3. From repo root or `backend/`, using the project venv:

```powershell
cd d:\ai-sdlc\backend
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

**What it verifies:** env presence, imports, Blob list under prefix, Document Intelligence `prebuilt-layout` on a tiny DOCX, Search index exists, OpenAI chat deployment, optional embeddings.

**Your todo:**

- [ ] Run `scripts/smoke_test.py` in **staging** until exit code **0**.

### Scripted workflow E2E (HTTP: upload → template → compile → workflow → download)

Use **[`scripts/staging_workflow_e2e.py`](../scripts/staging_workflow_e2e.py)** against your **deployed** API (same Azure-backed app as staging). It reads **`STAGING_BASE_URL`** and optional **`E2E_DOCUMENT_PATH`** / **`E2E_TEMPLATE_PATH`** from the environment (same `.env` as `smoke_test.py` is fine).

```powershell
cd d:\ai-sdlc\backend
# Point at your staging site (or http://127.0.0.1:8000 if API runs locally with Azure env)
$env:STAGING_BASE_URL = "https://your-staging-host.example.com"
$env:E2E_DOCUMENT_PATH = "D:\samples\requirements.pdf"
$env:E2E_TEMPLATE_PATH = "D:\templates\sdlc-template.docx"
.\.venv\Scripts\python.exe scripts\staging_workflow_e2e.py
```

**Optional env:** `E2E_POLL_INTERVAL_SEC`, `E2E_MAX_WAIT_SEC`, `E2E_OUTPUT_PATH`, `E2E_VERIFY_SSL=false` (dev only), `E2E_TEMPLATE_TYPE`, `E2E_TEMPLATE_VERSION`.

If document/template paths are omitted, the script uploads **minimal placeholders** (API wiring only; real Azure ingestion/compile may fail — use real files for a valid staging run).

- [ ] Run `staging_workflow_e2e.py` until it prints `DONE` and writes `e2e_staging_output.docx` (or `E2E_OUTPUT_PATH`).

**Note:** `smoke_test.py` now accepts **`.env.example`-style** names: `AZURE_DOCUMENT_INTELLIGENCE_*`, `AZURE_STORAGE_CONTAINER_NAME`, plus legacy short names.

---

## 3. Remaining production hygiene (no auth)

- [ ] **`APP_DEBUG=false`** in production/staging config.
- [ ] **CORS:** set `cors_origins` to your real front-end origin(s) if not localhost-only.
- [ ] **Reverse proxy:** SSE for `/api/workflow-runs/{id}/events` — idle timeouts long enough (often ≥ 120s for diagnostics).
- [ ] **Storage:** if multiple instances, confirm shared disk or Blob strategy (file-backed JSON repos).
- [ ] **Lint:** run `ruff check . --fix` in `backend/` and fix remaining issues (optional but recommended before go-live).
- [ ] **Starlette 422 deprecation** warning in tests — plan library upgrade or handler update when convenient.

---

## 4. Quick reference — commands

| Goal | Command |
|------|---------|
| Unit + integration tests | `cd d:\ai-sdlc` then `backend\.venv\Scripts\python.exe -m pytest backend/tests -q` |
| Azure smoke (staging) | `cd d:\ai-sdlc\backend` then `.\.venv\Scripts\python.exe scripts\smoke_test.py` |
| Coverage (from repo root) | `backend\.venv\Scripts\python.exe -m pytest backend/tests --cov=backend --cov-report=term-missing` |

---

*See also: [GO_LIVE_INSPECTION_REPORT.md](GO_LIVE_INSPECTION_REPORT.md) for the full phase audit.*
