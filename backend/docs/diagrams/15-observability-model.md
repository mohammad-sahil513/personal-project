# 15 - Observability Model Diagram

## Purpose
Show where logs, events, progress, and cost summaries are produced and consumed.

## Questions Answered
- Which components emit operational telemetry?
- How are workflow-level observability summaries built?
- Which endpoints expose observability to clients?

## Diagram

```mermaid
flowchart TD
    EXEC[WorkflowExecutorService] --> EVT[WorkflowEventService]
    EXEC --> PROG[Progress/Phase Updates]
    EXEC --> COST[Cost Aggregation + Summary]
    ING[Ingestion Runtime Bridge] --> COST
    RET[Retrieval Services] --> COST
    GEN[Generation Services] --> COST
    EVT --> STREAM[(Event Stream / Logs)]
    PROG --> META[(Workflow Metadata)]
    COST --> META
    META --> APIOBS[Observability API Endpoint]
    STREAM --> APIOBS
```

## Notes
- Observability summary consolidates ingestion, retrieval, and generation costs.
- Status, phase progression, and diagnostics are read back through workflow endpoints.
