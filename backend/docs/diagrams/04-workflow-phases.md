# 04 - Workflow Phases Diagram

## Purpose
Show the top-level end-to-end workflow pipeline phases.

## Questions Answered
- What is the full execution order?
- Which major lifecycle stages exist?
- Where does each request move over time?

## Diagram

```mermaid
flowchart LR
    P1[INPUT_PREPARATION] --> P2[INGESTION]
    P2 --> P3[TEMPLATE_PREPARATION]
    P3 --> P4[SECTION_PLANNING]
    P4 --> P5[RETRIEVAL]
    P5 --> P6[GENERATION]
    P6 --> P7[ASSEMBLY_VALIDATION]
    P7 --> P8[RENDER_EXPORT]
```

## Notes
- These phases map to progress planning and workflow execution services.
- Progress is weighted per phase and rolled up into overall workflow progress.
