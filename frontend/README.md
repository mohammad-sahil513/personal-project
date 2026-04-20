# AI SDLC — Frontend

React + TypeScript + Vite + Tailwind UI for the document generation workflow. It talks to the **FastAPI** backend using the real `/api` contract (`success_response` envelopes are unwrapped in the Axios client).

## Stack

- React 18, Vite 5, TypeScript
- Tailwind CSS (black / `#FFD400` theme)
- Zustand for client state
- Axios (`baseURL` from `VITE_API_BASE`, default `/api`)
- react-markdown + remark-gfm (section preview)
- lucide-react

## Setup

```bash
npm install
npm run dev
```

App dev server: **http://localhost:3000** (see `vite.config.ts`).

The dev server proxies `/api` to **`BACKEND_ORIGIN`**, then **`VITE_DEV_PROXY_TARGET`**, then **`http://127.0.0.1:8000`** (see [`vite.config.ts`](vite.config.ts)). Set one of those in `frontend/.env` to match `APP_HOST` / `APP_PORT` in `backend/.env`.

Copy optional env:

```bash
cp .env.example .env
```

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE` | API path prefix for Axios (default `/api`). In dev, the Vite dev server proxies `/api` to the backend. |
| `BACKEND_ORIGIN` or `VITE_DEV_PROXY_TARGET` | Dev-only: origin of the FastAPI server for the Vite proxy (not exposed to `import.meta.env`). |

## API flow (aligned with backend)

Responses use `{ success, message, data, ... }`; the client interceptor exposes **`data`** as `response.data` to callers.

1. `POST /api/documents/upload` — multipart `file` → `document_id`
2. For each selected deliverable type (PDD / SDD / UAT), `POST /api/workflow-runs` with  
   `{ document_id, template_id, "start_immediately": true }` — one workflow run per type (templates must match that type).
3. Poll `GET /api/workflow-runs/{workflow_run_id}/status` for each run until all `COMPLETED` or any `FAILED`.
4. Review: `GET /api/workflow-runs/{workflow_run_id}` → `assembled_document.sections` for markdown content.
5. Download: `GET /api/outputs/{output_id}/download` when the workflow exposes `output_id` and export is ready.

Templates:

- `GET /api/templates` → `{ items, total }`
- `POST /api/templates/upload` — form fields `file`, `template_type` (e.g. `PDD` / `SDD` / `UAT`), optional `version`
- `DELETE /api/templates/{template_id}` — remove template (metadata + `.docx` binary when present)

## Routes

| Route | Purpose |
|-------|---------|
| `/` | Upload BRD, select output types, pick one template per type |
| `/progress` | Aggregated progress for all workflow runs |
| `/output` | Tabs per deliverable, section sidebar, markdown viewer, per-type DOCX download |
| `/templates` | Template library + upload |

## Manual test checklist

1. Start backend on the proxied port (default 8000).
2. `npm run dev` in `frontend/`.
3. Upload a PDF/DOCX, ensure each selected PDD/SDD/UAT has a template (upload templates on `/templates` if needed).
4. Generate → progress → review → download DOCX when `output_id` is present.

## Notes

- **ZIP “download all”** is not implemented server-side; the UI exposes per-type DOCX downloads only.
- Refreshing the browser clears Zustand state; you will lose in-progress workflow IDs unless persistence is added later.
