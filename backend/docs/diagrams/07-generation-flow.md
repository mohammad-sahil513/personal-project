# 07 - Generation Flow Diagram

## Purpose
Show section-by-section generation using planned sections and retrieval outputs.

## Questions Answered
- How is generation orchestrated per section?
- How is section progress updated?
- What is stored after generation completes?

## Diagram

```mermaid
flowchart TD
    A[WorkflowExecutorService.run_section_generation] --> B{For each planned section}
    B --> C[Mark section RUNNING]
    C --> D[Publish section.generation.started]
    D --> E[WorkflowSectionGenerationService.run_generation_for_workflow]
    E --> F[SectionGenerationService.generate_for_section]
    F --> G[Store section result]
    G --> H[Mark section COMPLETED]
    H --> I[Publish section.generation.completed]
    I --> J[Recalculate overall progress]
    F -.error.-> K[Mark section FAILED + publish failed event]
    K --> L[handle_workflow_failure]
    J --> M[Attach section_generation_results]
```

## Notes
- Section outputs can be text, table, or diagram artifacts.
- Diagnostics and estimated costs are aggregated into observability.
