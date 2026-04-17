# 02 - Container Architecture Diagram

## Purpose
Show deployable/runtime containers and their interactions.

## Questions Answered
- What are the main runtime units?
- Which unit talks to storage and cloud services?
- How does background execution fit in?

## Diagram

```mermaid
flowchart TB
    Client[Frontend / API Consumer]
    APIC[API Container<br/>FastAPI routes + app services]
    BGC[Background Runtime<br/>TaskDispatcher + async workflow]
    LocalStore[(JSON Metadata / Output Artifacts / Logs)]
    Azure[(Azure Services)]

    Client --> APIC
    APIC --> BGC
    APIC --> LocalStore
    BGC --> LocalStore
    BGC --> Azure
    APIC --> Azure
```

## Notes
- API and background runtime may run in same process in current setup, but are separated logically here.
- Industrial scaling can split background runtime into dedicated worker processes.
