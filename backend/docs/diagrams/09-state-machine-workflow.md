# 09 - Workflow State Machine Diagram

## Purpose
Define allowed lifecycle transitions for a workflow run.

## Questions Answered
- What statuses can a workflow enter?
- Which transitions are terminal?
- When is a workflow considered done?

## Diagram

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RUNNING: dispatch_workflow_execution
    RUNNING --> COMPLETED: all phases finished
    RUNNING --> FAILED: handle_workflow_failure
    FAILED --> [*]
    COMPLETED --> [*]
```

## Notes
- `RUNNING` spans all major phases from input preparation through export.
- Any unrecoverable error path can force transition to `FAILED`.
