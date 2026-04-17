# 14 - Deployment Topology Diagram

## Purpose
Describe logical deployment topology across environments.

## Questions Answered
- Which runtime blocks exist in each environment?
- How does the backend interact with managed cloud services?
- Where do clients enter the system?

## Diagram

```mermaid
flowchart LR
    subgraph Clients
        FE[Frontend / API Consumers]
    end

    subgraph AppEnv[Application Environment]
        API[FastAPI Runtime]
        BG[Background Task Execution]
        FS[(Local/Attached File Storage)]
    end

    subgraph Azure[Azure Managed Services]
        Blob[Blob Storage]
        Search[AI Search]
        AOAI[OpenAI]
        DI[Document Intelligence]
    end

    FE --> API
    API --> BG
    API --> FS
    BG --> FS
    BG --> Blob
    BG --> Search
    BG --> AOAI
    BG --> DI
```

## Notes
- Current architecture can run API + background in one service process.
- Production hardening often separates worker runtime from API runtime.
