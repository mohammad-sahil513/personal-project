# Dependency Reports Index

This folder contains detailed module-level dependency reports for upstream/downstream mapping across backend and frontend.

## Files

- `00_SYSTEM_DEPENDENCY_OVERVIEW.md`
  - Cross-module flow from upload to final output.
  - Shared contracts, persistence surfaces, and integration hotspots.

- `01_INGESTION_DEPENDENCY_REPORT.md`
  - Ingestion file map, stage pipeline dependencies, and side effects.
  - Upstream triggers and downstream retrieval coupling.

- `02_TEMPLATE_PLANNING_RETRIEVAL_REPORT.md`
  - Template preparation, section planning, retrieval runtime and contracts.
  - API and frontend consumers tied to these phases.

- `03_GENERATION_ASSEMBLY_EXPORT_REPORT.md`
  - Generation runtime, assembly flow, export and output APIs.
  - Frontend output dependencies and completion assumptions.

- `04_PRACTICAL_GAPS_AND_RISKS_APPENDIX.md`
  - Consolidated practical gaps and known risks/mismatches.
  - Prioritized actions for implementation hardening.
- `05_PHASE_TRACEABILITY_MATRIX.md`
  - Phase-by-phase traceability matrix:
    `phase -> API -> service -> module -> artifact -> frontend consumer`.

## Recommended Reading Order

1. `00_SYSTEM_DEPENDENCY_OVERVIEW.md`
2. `01_INGESTION_DEPENDENCY_REPORT.md`
3. `02_TEMPLATE_PLANNING_RETRIEVAL_REPORT.md`
4. `03_GENERATION_ASSEMBLY_EXPORT_REPORT.md`
5. `04_PRACTICAL_GAPS_AND_RISKS_APPENDIX.md`
6. `05_PHASE_TRACEABILITY_MATRIX.md`
