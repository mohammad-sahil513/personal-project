# 13 - API Sequence: Create Workflow

## Purpose
Show the request/response and asynchronous dispatch path for workflow creation.

## Questions Answered
- What happens after `POST /workflow-runs`?
- Where is async execution started?
- What is returned immediately vs processed in background?

## Diagram

```mermaid
sequenceDiagram
    participant U as Client
    participant R as Workflow Route
    participant WS as WorkflowService
    participant WES as WorkflowExecutorService
    participant TD as TaskDispatcher
    participant BG as Background Runtime

    U->>R: POST /workflow-runs
    R->>WS: create_workflow(document_id, template_id)
    WS-->>R: created workflow_run_id
    R->>WES: dispatch_workflow_execution(workflow_run_id)
    WES->>TD: dispatch(execute_workflow_skeleton)
    TD-->>WES: dispatch_mode
    WES-->>R: RUNNING status payload
    R-->>U: 200 + workflow metadata + dispatch_mode
    TD->>BG: execute in background
```

## Notes
- API responds without waiting for entire workflow completion.
- Subsequent status/sections/observability endpoints expose progress and outputs.
