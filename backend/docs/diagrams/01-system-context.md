# 01 - System Context Diagram

## Purpose
Show the project boundary, primary actors, and external dependencies.

## Questions Answered
- Who uses the backend?
- Which external systems does it rely on?
- Where do outputs and metadata persist?

## Diagram

```mermaid
flowchart LR
    User[Client / Frontend]
    API[Backend API]
    Worker[Workflow Background Execution]
    Blob[Azure Blob Storage]
    Search[Azure AI Search]
    AOAI[Azure OpenAI]
    DI[Azure Document Intelligence]
    Files[(Local Metadata / Outputs / Logs)]

    User --> API
    API --> Worker
    API --> Files
    Worker --> Files
    Worker --> Blob
    Worker --> Search
    Worker --> AOAI
    Worker --> DI
```

## Notes
- API starts workflow runs and exposes status/output endpoints.
- Worker path represents async execution via dispatcher/background mechanisms.
- Cloud dependencies are concentrated in ingestion/retrieval/generation runtime paths.
