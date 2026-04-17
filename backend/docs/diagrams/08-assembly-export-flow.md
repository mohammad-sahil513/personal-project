# 08 - Assembly and Export Flow Diagram

## Purpose
Show how generated sections become the final exported DOCX artifact.

## Questions Answered
- How are section outputs assembled?
- How is output metadata prepared and finalized?
- What marks workflow completion at document level?

## Diagram

```mermaid
flowchart TD
    A[assemble_generated_sections] --> B[DocumentAssemblyService.build_assembled_document]
    B --> C[Attach assembled_document to workflow]
    C --> D[Publish workflow.assembled]
    D --> E[prepare_output_export]
    E --> F[OutputExportService.prepare_docx_export]
    F --> G[Attach output_id to workflow]
    G --> H[render_and_finalize_output]
    H --> I[OutputExportService.export_docx]
    I --> J[DocxRendererService.render]
    J --> K[OutputService.mark_output_ready]
    K --> L[Publish output.ready]
```

## Notes
- Assembly validates all planned sections have generation outputs.
- Export path persists both output metadata and physical DOCX artifact path.
