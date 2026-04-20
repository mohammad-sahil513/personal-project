# Gaps and Mismatches Report

This report summarizes practical gaps and known integration risks observed across the current backend and frontend implementation.

## Practical Gaps

### 1) Workflow execution is not fully chained from API start
- `POST /workflow-runs` can dispatch execution, but the primary runtime path currently emphasizes input preparation + ingestion.
- Later phases (section planning, retrieval, generation, assembly, export) exist in services but are not consistently chained in the same API-triggered path.
- Practical impact: frontend may keep polling while waiting for `COMPLETED` + `output_id`.

### 2) Frontend runtime visibility relies on polling only
- Backend provides workflow SSE events, but frontend currently uses status polling and does not consume live EventSource streams.
- Practical impact: slower UI feedback, more API calls, and less granular in-flight diagnostics.

### 3) Contract drift in response field naming
- Document metadata uses `uploaded_at` in backend DTOs while frontend types also reference `created_at` as optional.
- Practical impact: low immediate break risk, but higher long-term confusion and maintenance cost.

### 4) Silent error handling in critical UI paths
- Progress/output flows contain broad catch blocks that suppress actionable error details.
- Practical impact: users see stalled behavior without clear recovery guidance.

### 5) Low automated quality gates on frontend
- Frontend setup has TypeScript strict checks, but limited/no built-in lint and test enforcement in project scripts.
- Practical impact: regressions can pass without consistent pre-merge checks.

## Known Risks and Mismatches

### 1) Unmounted generation route
- `generation_routes` exists but is not mounted in the main API router.
- It also contains path patterns that can conflict with global API prefixing if mounted without normalization.
- Risk: dead endpoint expectations, inconsistent documentation vs runtime behavior.

### 2) Partial workflow chaining
- Core orchestrator methods for retrieval/generation/assembly/export exist, but the active create-and-start flow can stop after ingestion-focused execution.
- Risk: workflow records may not progress to final output generation in all runtime paths.

### 3) API prefix/version drift risk
- Current backend and frontend defaults align on `/api`, but stale assumptions (for example historical `/api/v1` usage in examples/tests) can cause environment misconfiguration.
- Risk: integration failures caused by base URL mismatches rather than business logic.

### 4) SSE payload and event naming consistency concerns
- Event payload formatting and phase labels are not fully standardized across all producers/consumers.
- Risk: future frontend SSE adoption may require compatibility cleanup first.

### 5) In-memory event stream state
- Workflow event broker state is process-memory based.
- Risk: restart/failover loses stream history and active subscriber continuity.

### 6) File-based persistence scalability constraints
- Current JSON/file persistence model is simple and effective for local/dev usage.
- Risk: concurrent writes and horizontal scaling introduce synchronization and durability concerns.

## Priority Recommendations

1. **Chain the full workflow path** in the API-triggered execution flow through export completion.
2. **Mount/fix generation routes** or formally deprecate them to remove dead-path ambiguity.
3. **Normalize contracts** (`uploaded_at` vs `created_at`, event naming, phase labels) and document a single canonical schema.
4. **Strengthen frontend resilience** by surfacing actionable errors and adding test/lint CI gates.
5. **Decide on event strategy**: polling-only (documented) or production SSE support with standardized payloads.
