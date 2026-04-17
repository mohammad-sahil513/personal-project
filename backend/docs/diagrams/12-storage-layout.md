# 12 - Storage Layout Diagram

## Purpose
Map persistent storage categories and what each stores.

## Questions Answered
- Where are workflow and execution records stored?
- Where are binaries and generated outputs stored?
- How are logs/artifacts separated from metadata?

## Diagram

```mermaid
flowchart TD
    APP[Backend Services]
    META[(Workflow / Execution / Template / Output Metadata JSON)]
    DOCBIN[(Document Binary Files)]
    OUT[(Rendered Output Files - DOCX and Artifacts)]
    LOGS[(Run Logs / Observability Artifacts)]
    CLOUD[(Azure Blob / Search Indices)]

    APP --> META
    APP --> DOCBIN
    APP --> OUT
    APP --> LOGS
    APP --> CLOUD
```

## Notes
- Metadata repositories are file-based JSON in the current architecture.
- Export renderer produces filesystem artifacts while cloud indexing stores retrieval-ready vectors.
