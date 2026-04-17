# 06 - Retrieval Flow Diagram

## Purpose
Show section-level retrieval orchestration from section plan to evidence bundle.

## Questions Answered
- How are sections retrieved one by one?
- Where are retrieval events emitted?
- What artifact is persisted for downstream generation?

## Diagram

```mermaid
flowchart TD
    A[WorkflowSectionRetrievalService.run_retrieval_for_workflow] --> B{For each section}
    B --> C[Publish section.retrieval.started]
    C --> D[SectionRetrievalService.retrieve_for_section]
    D --> E[Retrieval runtime via live wiring]
    E --> F[Build retrieval result dict]
    F --> G[Publish section.retrieval.completed]
    G --> H[Persist in section_retrieval_results]
    D -.error.-> I[Publish section.retrieval.failed]
```

## Notes
- Retrieval output includes diagnostics, evidence bundle, confidence, warnings, and cost summary.
- `section_retrieval_results` is the direct input for generation.
