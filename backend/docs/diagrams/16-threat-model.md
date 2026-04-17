# 16 - Threat Model Diagram

## Purpose
Capture trust boundaries and high-level security risk surfaces.

## Questions Answered
- Where are trust boundaries in this architecture?
- Which paths carry sensitive document content?
- Which integrations require strict credential and access controls?

## Diagram

```mermaid
flowchart LR
    subgraph TB1[Boundary 1: Untrusted Client Zone]
        C[Client / Caller]
    end

    subgraph TB2[Boundary 2: Trusted Backend Zone]
        API[API Layer]
        APP[Application/Worker Layer]
        STORE[(Local Metadata + Artifacts)]
    end

    subgraph TB3[Boundary 3: External Managed Services]
        Blob[Blob Storage]
        Search[AI Search]
        AOAI[OpenAI]
        DI[Document Intelligence]
    end

    C --> API
    API --> APP
    APP --> STORE
    APP --> Blob
    APP --> Search
    APP --> AOAI
    APP --> DI
```

## Notes
- Key controls to document per boundary: authN/authZ, input validation, secret handling, encryption, logging, and retention.
- PII-sensitive paths are concentrated in ingestion and should have explicit masking/audit controls.
