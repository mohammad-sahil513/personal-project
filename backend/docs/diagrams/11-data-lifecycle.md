# 11 - Data Lifecycle Diagram

## Purpose
Show how data transforms from uploaded document to final exported output.

## Questions Answered
- What are the major data transformation checkpoints?
- Which artifacts feed retrieval and generation?
- What is the final consumable deliverable?

## Diagram

```mermaid
flowchart LR
    A[Uploaded Document] --> B[Parsed Document Content]
    B --> C[PII Masked Content]
    C --> D[Sectioned Structure]
    D --> E[Semantic Chunks]
    E --> F[Indexed Vectors]
    F --> G[Retrieval Evidence Bundles]
    G --> H[Generated Section Outputs]
    H --> I[Assembled Document]
    I --> J[Final DOCX Output]
```

## Notes
- Retrieval operates on indexed chunks and metadata-backed evidence.
- Generation consumes retrieval outputs per section and produces structured artifacts.
