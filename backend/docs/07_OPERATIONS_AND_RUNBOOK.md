# 07 - Operations and Runbook

## Environment Configuration

Primary configuration source:
- `.env` file
- `core/config.py` settings model

Key setting groups:

- App/runtime:
  - `app_name`, `app_env`, `app_debug`, `app_host`, `app_port`, `api_prefix`
- Storage:
  - `local_storage_root`, directory names for workflow/document/template/output/execution/logs
- Azure OpenAI:
  - endpoint, api key, deployments, API version
- Azure Document Intelligence:
  - endpoint, key
- Azure AI Search:
  - endpoint, key, index name, vector field
- Azure Blob Storage:
  - connection/account URL, container, root prefix

## Startup Behavior

On app startup:

1. Logging is configured.
2. Required storage directories are created if missing.
3. Middleware is installed for request correlation IDs.
4. CORS and exception handlers are enabled.
5. API router is attached.

## Request Correlation

- Incoming `X-Request-Id` is reused when present.
- If missing, a new request ID is generated.
- ID is added back to response header and available in logging context.

## Background Execution Modes

Task dispatch order:

1. FastAPI `BackgroundTasks`
2. `asyncio.create_task`
3. `asyncio.run` fallback

This behavior is implemented in `workers/task_dispatcher.py`.

## Production Readiness Checks

- `GET /health` should return healthy status.
- `GET /ready` should confirm runtime environment and storage root.
- Workflow SSE endpoint should stream events for active runs.
- Output download endpoint should enforce `READY` status checks.

## Operational Troubleshooting

## Workflow stuck in running
- Check `/workflow-runs/{id}/status`.
- Check `/workflow-runs/{id}/events`.
- Check `/workflow-runs/{id}/observability`.
- Verify ingestion execution state and current stage.

## Missing output file
- Confirm output record status is `READY`.
- Validate artifact path exists on disk.
- Re-check export step and renderer logs.

## Retrieval/generation quality issues
- Inspect diagnostics from workflow observability.
- Check retrieval evidence quality and section-level warnings.
- Verify model deployment settings and cloud credentials.

## Config/bootstrap issues
- Validate required Azure environment variables.
- Verify storage paths and permissions.
- Confirm readiness endpoint reports expected environment values.

## Suggested Operational Extensions

- Add queue-backed workers for high concurrency deployments.
- Add structured metrics (latency, failure rate, queue depth).
- Add alert thresholds on phase failure rate and output export failures.
- Add retention/cleanup policies for logs and artifacts.
