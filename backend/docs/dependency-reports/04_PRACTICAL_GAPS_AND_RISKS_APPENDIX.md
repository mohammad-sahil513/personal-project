# Practical Gaps and Risks Appendix

This appendix consolidates practical gaps and known mismatches across the workflow pipeline.

## Practical Gaps

### 1) Partial API-triggered workflow chaining
- `POST /workflow-runs` dispatches execution, but active path can emphasize ingestion without consistently chaining all downstream phases.
- Effect: workflows may not always reach assembled output and export-ready state.

### 2) Frontend runtime visibility is polling-centric
- Backend exposes SSE events, but frontend currently uses status polling only.
- Effect: weaker real-time diagnostics and slower UX responsiveness.

### 3) Contract drift and naming inconsistencies
- Cross-layer field naming differences (for example timestamp naming variants) increase ambiguity.
- Effect: avoidable adapter logic and brittle assumptions in clients/tests.

### 4) Silent/low-context error handling in UI flow
- Some async call sites suppress detailed errors.
- Effect: stalled states are harder to diagnose for users and maintainers.

### 5) Uneven verification depth
- Backend has significant tests, but frontend has limited automated safety nets in project scripts.
- Effect: regressions in UI flow or integration assumptions can slip through.

## Known Risks and Mismatches

### 1) Unmounted generation route module
- `backend/api/routes/generation_routes.py` exists but is not mounted in `backend/api/router.py`.
- Additional risk: path prefix duplication if mounted without normalizing route prefixes.

### 2) Template artifact expectation mismatch
- Compile runtime and artifact download expectations for manifest/shell artifacts are not always aligned.
- Risk: artifact download endpoints may return missing/unavailable outputs in some compile paths.

### 3) In-memory event broker durability limits
- Workflow event service keeps stream state in-process.
- Risk: restart/failover resets event continuity and recent-event history.

### 4) File-based persistence scaling constraints
- Repository model is file JSON + local artifacts.
- Risk: concurrent writes and horizontal scaling need stronger coordination guarantees.

### 5) Workflow phase/event naming variance
- Some phase/event labels differ in casing or canonical naming across sources.
- Risk: consumers need normalization logic, and monitoring/reporting can fragment.

## Priority Actions

1. Chain full workflow execution in one API-triggered path through export completion.
2. Resolve generation route mounting and prefix normalization.
3. Standardize cross-layer contracts and event phase naming.
4. Improve frontend error surfacing and add test/lint guardrails.
5. Decide and document event strategy (polling-only vs SSE-enabled UX).
