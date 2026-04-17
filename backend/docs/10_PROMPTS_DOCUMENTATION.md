# 10 - Prompts Documentation

This document catalogs prompt assets used by ingestion, generation, and template compilation flows.

## Prompt Folder Structure

- `prompts/ingestion/`
- `prompts/generation/`
  - `summarize_text/`
  - `generate_table/`
  - `diagram_plantuml/`
- `prompts/template/`

## `prompts/ingestion/`

- `pii_classification_v1.yaml` - prompt for PII classification stage.
- `vision_generic_v1.yaml` - prompt for vision extraction/classification use-cases.

## `prompts/generation/summarize_text/`

Default:
- `default.yaml`

Topic-focused text summaries:
- `overview.yaml`
- `system_overview.yaml`
- `architecture.yaml`
- `system_design.yaml`
- `requirements.yaml`
- `acceptance_criteria.yaml`
- `non_functional_requirements.yaml`
- `integration_points.yaml`
- `data_flow.yaml`
- `deployment_strategy.yaml`
- `operations_runbook.yaml`
- `security_controls.yaml`
- `compliance_controls.yaml`
- `operational_readiness.yaml`
- `scope.yaml`
- `assumptions.yaml`
- `constraints.yaml`
- `risks.yaml`

## `prompts/generation/generate_table/`

Default:
- `default.yaml`

Table-focused generation:
- `matrix.yaml`
- `mapping.yaml`
- `catalog.yaml`
- `traceability_matrix.yaml`
- `test_coverage.yaml`
- `api_specification.yaml`
- `data_model.yaml`
- `risk_register_table.yaml`
- `api_matrix.yaml`
- `integration_matrix.yaml`
- `nfr_matrix.yaml`

## `prompts/generation/diagram_plantuml/`

Default:
- `default.yaml`

Diagram-focused generation:
- `architecture.yaml`
- `component.yaml`
- `deployment.yaml`
- `sequence.yaml`
- `flowchart.yaml`
- `data_flow_diagram.yaml`
- `system_context_diagram.yaml`

## `prompts/template/`

- `ai_compiler_v1.yaml` - template AI compile instructions.
- `correction_loop_v1.yaml` - correction/refinement loop prompt.

## Prompt Usage Notes

- Prompt key selection should align with section generation strategy and requested output type.
- Keep prompt versioning explicit when changing semantics.
- For production stability, avoid silent prompt changes without changelog notes.

## Prompt Change Management Checklist

- Track prompt file name and version in commit messages.
- Record expected behavior delta (quality, format, strictness).
- Validate with targeted integration tests (retrieval/generation/template compile).
- Keep fallback defaults (`default.yaml`) stable and backward compatible.
