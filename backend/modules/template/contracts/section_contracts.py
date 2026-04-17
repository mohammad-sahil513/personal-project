"""
Section-level template contracts.

These models represent:
- declarative section definitions inside template JSON,
- retrieval binding metadata for the resolver layer,
- the normalized ResolvedSection handoff used by downstream generation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models.template_enums import GenerationStrategy, NoEvidencePolicy
from .template_contracts import GroundingPolicy, PromptReference, RetrievalOverrideConfig


class SectionValidationRules(BaseModel):
    """Template-side validation rules that downstream generation can enforce."""

    model_config = ConfigDict(extra="forbid")

    min_words: int | None = Field(default=None, ge=0)
    max_words: int | None = Field(default=None, ge=1)
    required_columns: list[str] = Field(default_factory=list)
    min_rows: int | None = Field(default=None, ge=0)
    banned_phrases: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_word_bounds(self) -> "SectionValidationRules":
        """Ensure min/max word limits are internally consistent."""
        if self.min_words is not None and self.max_words is not None and self.min_words > self.max_words:
            raise ValueError("`min_words` cannot exceed `max_words`.")
        return self


class RetrievalBinding(BaseModel):
    """
    Retrieval binding declared by a template section.

    This is intentionally lightweight in Phase 1:
    - it can refer to a named profile,
    - or carry an inline retrieval-plan fragment for the resolver to interpret later.
    """

    model_config = ConfigDict(extra="forbid")

    profile_name: str | None = Field(default=None, min_length=1)
    inline_plan: dict[str, Any] | None = Field(default=None)
    section_heading: str | None = Field(default=None, min_length=1)
    section_intent: str | None = Field(default=None, min_length=1)
    semantic_role: str | None = Field(default=None, min_length=1)
    filters: dict[str, Any] = Field(default_factory=dict)
    overrides: RetrievalOverrideConfig | None = Field(default=None)

    @model_validator(mode="after")
    def validate_resolution_source(self) -> "RetrievalBinding":
        """
        A retrieval binding must define at least one resolution source:
        - named profile, or
        - inline plan.
        """
        if not self.profile_name and not self.inline_plan:
            raise ValueError("A retrieval binding must define `profile_name` or `inline_plan`.")
        return self


class TemplateSection(BaseModel):
    """Declarative section definition found inside a template artifact."""

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    generation_strategy: GenerationStrategy
    prompt: PromptReference
    retrieval: RetrievalBinding | None = Field(default=None)
    grounding_policy: GroundingPolicy | None = Field(default=None)
    validation_rules: SectionValidationRules = Field(default_factory=SectionValidationRules)
    dependencies: list[str] = Field(default_factory=list)
    no_evidence_policy: NoEvidencePolicy = Field(default=NoEvidencePolicy.DEGRADE)
    order_hint: int | None = Field(
        default=None,
        ge=0,
        description="Optional author-provided order hint before dependency sorting.",
    )

    @model_validator(mode="after")
    def validate_dependencies_do_not_self_reference(self) -> "TemplateSection":
        """Disallow trivial self-dependencies at contract level."""
        if self.section_id in self.dependencies:
            raise ValueError("A section cannot depend on itself.")
        return self


class ResolvedSection(BaseModel):
    """
    Normalized Template → Generation handoff object.

    This mirrors the final aligned architecture where downstream generation
    consumes resolved section metadata rather than raw template JSON.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str
    title: str
    execution_order: int = Field(..., ge=0)
    generation_strategy: GenerationStrategy
    prompt_key: str = Field(..., min_length=1)
    slots_required: list[str] = Field(default_factory=list)
    slots_optional: list[str] = Field(default_factory=list)
    retrieval_profile_name: str | None = Field(default=None)
    inline_retrieval_plan: dict[str, Any] | None = Field(default=None)
    merged_retrieval_overrides: RetrievalOverrideConfig | None = Field(default=None)
    grounding_policy: GroundingPolicy
    validation_rules: SectionValidationRules = Field(default_factory=SectionValidationRules)
    dependencies: list[str] = Field(default_factory=list)
    no_evidence_policy: NoEvidencePolicy = Field(default=NoEvidencePolicy.DEGRADE)
    runtime_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_slot_expectations(self) -> "ResolvedSection":
        """Ensure the resolved prompt contract still requires SOURCE evidence."""
        if "source_evidence" not in self.slots_required:
            raise ValueError("Resolved sections must require `source_evidence`.")
        return self


# -----------------------------------------------------------------------------
# Complementary forward-reference rebuild
# -----------------------------------------------------------------------------
# This keeps TemplateDefinition safe even if import order changes in the future.
try:
    from .template_contracts import TemplateDefinition  # pylint: disable=cyclic-import

    TemplateDefinition.model_rebuild(_types_namespace={"TemplateSection": TemplateSection})
except ImportError:
    pass