# 03 - Layered Architecture Diagram

## Purpose
Show code-level layering and dependency direction.

## Questions Answered
- Where should business logic live?
- Which layers can call which layers?
- How are persistence and external integrations separated?

## Diagram

```mermaid
flowchart TD
    A[API Layer<br/>routes, schemas, dependencies]
    B[Application Layer<br/>workflow, ingestion bridge, section services]
    C1[Repository Layer<br/>workflow/document/output/execution persistence]
    C2[Infrastructure Layer<br/>Azure OpenAI/Search/SDK adapters]
    C3[Worker Layer<br/>TaskDispatcher, BackgroundRunner]
    D1[(Metadata Storage)]
    D2[(Artifacts Storage)]
    E[External Cloud Services]

    A --> B
    B --> C1
    B --> C2
    B --> C3
    C1 --> D1
    C1 --> D2
    C2 --> E
```

## Notes
- `repositories` own local persistence contracts.
- `infrastructure` owns external service adapters.
- `workers` owns async dispatch mechanics.
