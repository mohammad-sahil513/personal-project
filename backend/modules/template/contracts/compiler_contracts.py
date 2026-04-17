"""
Compiler-path contracts for custom template ingestion.

These models support the future implementation of:
- deterministic DOCX structure extraction,
- heading normalization,
- heuristic mapping,
- AI-assisted mapping for ambiguous sections,
- correction loops,
- final compiled artifact metadata.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models.template_enums import CompilerArtifactType, CompilerDecisionSource


class ExtractedHeading(BaseModel):
    """A single heading-like structure extracted from a custom DOCX template."""

    model_config = ConfigDict(extra="forbid")

    raw_text: str = Field(..., min_length=1)
    normalized_text: str = Field(..., min_length=1)
    level: int = Field(..., ge=1, le=9)
    order_index: int = Field(..., ge=0)
    source_anchor_hint: str | None = Field(default=None)


class ExtractedDocxStructure(BaseModel):
    """Deterministic extraction result from a custom template DOCX."""

    model_config = ConfigDict(extra="forbid")

    headings: list[ExtractedHeading] = Field(default_factory=list)
    contains_tables: bool = False
    contains_headers_footers: bool = False
    contains_multiple_sections: bool = False


class HeuristicMappingCandidate(BaseModel):
    """A possible section mapping proposed by the heuristic mapper."""

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)


class HeuristicMappingResult(BaseModel):
    """Heuristic mapping output for one extracted heading."""

    model_config = ConfigDict(extra="forbid")

    heading: ExtractedHeading
    candidates: list[HeuristicMappingCandidate] = Field(default_factory=list)
    selected_section_id: str | None = Field(default=None)
    decision_source: CompilerDecisionSource = Field(default=CompilerDecisionSource.HEURISTIC)


class AICompilerSuggestion(BaseModel):
    """AI-assisted mapping suggestion for ambiguous or weakly matched headings."""

    model_config = ConfigDict(extra="forbid")

    heading_text: str = Field(..., min_length=1)
    suggested_section_id: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    decision_source: CompilerDecisionSource = Field(default=CompilerDecisionSource.AI)


class DefaultsInjectionResult(BaseModel):
    """Result of injecting default policies/config into a compiled template."""

    model_config = ConfigDict(extra="forbid")

    defaults_applied: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SemanticValidationResult(BaseModel):
    """Semantic validation output for compiled template artifacts."""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CorrectionLoopResult(BaseModel):
    """Result of a bounded correction pass over a compiled template artifact."""

    model_config = ConfigDict(extra="forbid")

    corrected: bool = False
    iterations_used: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)


class CompilerArtifactReference(BaseModel):
    """Blob/file-backed artifact metadata for compiler outputs."""

    model_config = ConfigDict(extra="forbid")

    artifact_type: CompilerArtifactType
    path: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)


class CompiledTemplateArtifact(BaseModel):
    """
    Final compiler artifact set.

    Atomic version sync across template JSON, layout manifest, and shell DOCX
    will be enforced more fully in later phases; Phase 1 captures the metadata shape.
    """

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    template_json: CompilerArtifactReference
    layout_manifest: CompilerArtifactReference | None = None
    shell_docx: CompilerArtifactReference | None = None

    @model_validator(mode="after")
    def validate_version_sync(self) -> "CompiledTemplateArtifact":
        """
        Ensure all declared artifact references match the parent version string.
        This keeps the atomic version-sync rule visible from the contract layer.
        """
        references = [self.template_json, self.layout_manifest, self.shell_docx]
        mismatched = [ref.path for ref in references if ref is not None and ref.version != self.version]
        if mismatched:
            raise ValueError(
                "All compiler artifact references must use the same version as the parent artifact."
            )
        return self