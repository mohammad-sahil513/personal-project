"""
Template module enums and typed constants.

This file intentionally contains only lightweight enum definitions that are
safe to import from anywhere in the Template module without creating service-
level coupling.

Phase 1 goal:
- Define stable enum values for template contracts.
- Keep diagram strategy aligned with the current downstream-compatible state.
"""

from __future__ import annotations

from enum import StrEnum


class TemplateType(StrEnum):
    """Supported template source types."""

    STANDARD = "standard"
    CUSTOM = "custom"


class GenerationStrategy(StrEnum):
    """
    Section generation strategies understood by the template layer.

    Notes:
    - `diagram_plantuml` remains contract-valid for compatibility.
    - Runtime enablement is intentionally deferred in the current aligned plan.
    """

    SUMMARIZE_TEXT = "summarize_text"
    GENERATE_TABLE = "generate_table"
    DIAGRAM_PLANTUML = "diagram_plantuml"


class PromptSlotKey(StrEnum):
    """Prompt slot names shared across template and downstream generation."""

    SOURCE_EVIDENCE = "source_evidence"
    EXEMPLAR_EVIDENCE = "exemplar_evidence"
    GUIDELINE_EVIDENCE = "guideline_evidence"
    ROLLING_CONTEXT = "rolling_context"


class NoEvidencePolicy(StrEnum):
    """Allowed outcomes when SOURCE evidence is unavailable or insufficient."""

    FAIL = "fail"
    SKIP = "skip"
    DEGRADE = "degrade"
    BEST_EFFORT = "best_effort"


class ValidationSeverity(StrEnum):
    """Typed severity used by template validation results."""

    ERROR = "error"
    WARNING = "warning"


class TemplateValidationCode(StrEnum):
    """Common validation issue codes for template schema and semantics."""

    INVALID_FILTER_KEY = "invalid_filter_key"
    INVALID_OVERRIDE_KEY = "invalid_override_key"
    INVALID_STRATEGY = "invalid_strategy"
    UNIMPLEMENTED_STRATEGY = "unimplemented_strategy"
    CONDITIONAL_RUNTIME_SUPPORT = "conditional_runtime_support"
    INVALID_SLOT_CONFIGURATION = "invalid_slot_configuration"
    INVALID_GROUNDING_POLICY = "invalid_grounding_policy"
    INVALID_DEPENDENCY = "invalid_dependency"
    INVALID_RETRIEVAL_BINDING = "invalid_retrieval_binding"
    INVALID_COMPILER_OUTPUT = "invalid_compiler_output"


class CompilerDecisionSource(StrEnum):
    """Indicates how a custom-template section mapping was produced."""

    HEURISTIC = "heuristic"
    AI = "ai"
    DEFAULT = "default"
    CORRECTED = "corrected"


class CompilerArtifactType(StrEnum):
    """Artifact types produced by the custom template compiler path."""

    COMPILED_TEMPLATE_JSON = "compiled_template_json"
    LAYOUT_MANIFEST = "layout_manifest"
    SHELL_DOCX = "shell_docx"