"""
Top-level template contracts.

These contracts define the shared schema used by:
- template loading,
- template validation,
- template resolution,
- custom-template compilation outputs.

Design notes:
- `minimum_sources` is intentionally not supported.
- Prompt slots enforce SOURCE evidence as required.
- Contracts are configured with `extra="forbid"` to catch schema drift early.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..models.template_config import ALL_PROMPT_SLOTS, OPTIONAL_PROMPT_SLOTS
from ..models.template_enums import PromptSlotKey, TemplateType

if TYPE_CHECKING:
    from .section_contracts import TemplateSection


class TemplateMetadata(BaseModel):
    """Identifying information for a template artifact."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    template_id: str = Field(..., min_length=1, description="Unique template identifier.")
    name: str = Field(..., min_length=1, description="Human-readable template name.")
    version: str = Field(..., min_length=1, description="Template version string.")
    template_type: TemplateType = Field(..., description="Whether template is standard or custom.")
    description: str | None = Field(default=None, description="Optional template description.")


class GroundingPolicy(BaseModel):
    """
    Grounding controls for a template or section.

    `evidence_confidence_floor` is the template-layer field that later maps to
    retrieval `min_confidence`.
    """

    model_config = ConfigDict(extra="forbid")

    strict_grounding: bool = Field(
        default=True,
        description="Whether the generator must stay strictly grounded in evidence.",
    )
    allow_inference: bool = Field(
        default=False,
        description="Whether limited inference is allowed when evidence is thin.",
    )
    citation_required: bool = Field(
        default=True,
        description="Whether citations/traceability are required downstream.",
    )
    evidence_confidence_floor: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum acceptable evidence confidence at template layer.",
    )


class PromptReference(BaseModel):
    """
    Prompt contract reference for a template or section.

    The actual prompt content remains outside the Template contracts.
    This model only captures the key and slot semantics.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_key: str = Field(..., min_length=1, description="Prompt library key.")
    slot_keys: list[str] = Field(
        default_factory=lambda: sorted(ALL_PROMPT_SLOTS),
        description="All recognized slot keys for this prompt.",
    )
    slots_required: list[str] = Field(
        default_factory=lambda: [PromptSlotKey.SOURCE_EVIDENCE.value],
        description="Slots that must be supplied to execute the prompt.",
    )
    slots_optional: list[str] = Field(
        default_factory=lambda: sorted(OPTIONAL_PROMPT_SLOTS),
        description="Slots that may be provided when available.",
    )

    @field_validator("slot_keys", "slots_required", "slots_optional")
    @classmethod
    def _ensure_unique_items(cls, value: list[str]) -> list:
        """Prevent duplicate slot declarations inside the same list."""
        if len(value) != len(set(value)):
            raise ValueError("Slot lists must not contain duplicates.")
        return value

    @model_validator(mode="after")
    def validate_slot_contract(self) -> "PromptReference":
        """
        Enforce the locked prompt slot contract:
        - SOURCE evidence is always required.
        - Required and optional slots must not overlap.
        - All declared slots must come from the known prompt slot universe.
        """
        if PromptSlotKey.SOURCE_EVIDENCE.value not in self.slots_required:
            raise ValueError("`source_evidence` must always be listed in `slots_required`.")

        unknown_slots = (set(self.slot_keys) | set(self.slots_required) | set(self.slots_optional)) - set(
            ALL_PROMPT_SLOTS
        )
        if unknown_slots:
            raise ValueError(f"Unknown prompt slot(s): {sorted(unknown_slots)}")

        overlap = set(self.slots_required) & set(self.slots_optional)
        if overlap:
            raise ValueError(f"Required and optional slots must not overlap: {sorted(overlap)}")

        declared_union = set(self.slots_required) | set(self.slots_optional)
        if declared_union != set(self.slot_keys):
            raise ValueError(
                "`slot_keys` must exactly match the union of `slots_required` and `slots_optional`."
            )

        return self


class RetrievalOverrideConfig(BaseModel):
    """
    Template-defined retrieval override configuration.

    Note:
    - Template contract may carry custom-only fields like `final_output_top_k`.
    - The validator service will later enforce standard-vs-custom restrictions.
    """

    model_config = ConfigDict(extra="forbid")

    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1)
    final_output_top_k: int | None = Field(default=None, ge=1)
    fallback_policy: str | None = Field(default=None, min_length=1)
    exemplar_top_k: int | None = Field(default=None, ge=1)
    guideline_top_k: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_override_relationships(self) -> "RetrievalOverrideConfig":
        """
        Validate only relationships that are always true at the contract layer.

        The validator service will later apply template-type-specific policies.
        """
        if (
            self.top_k is not None
            and self.final_output_top_k is not None
            and self.final_output_top_k > self.top_k
        ):
            raise ValueError(
                "`final_output_top_k` must not exceed `top_k` when both values are provided."
            )
        return self


class TemplateDefinition(BaseModel):
    """Top-level template definition used by loader/validator/resolver flows."""

    model_config = ConfigDict(extra="forbid")

    metadata: TemplateMetadata
    default_grounding_policy: GroundingPolicy = Field(
        default_factory=GroundingPolicy,
        description="Default grounding policy inherited by sections unless overridden.",
    )
    sections: list["TemplateSection"] = Field(
        ...,
        min_length=1,
        description="Ordered list of template sections before dependency sorting.",
    )
    metadata_extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional safe extension metadata for artifact tracking.",
    )

    @model_validator(mode="after")
    def validate_section_ids_unique(self) -> "TemplateDefinition":
        """Ensure section IDs are unique within a template definition."""
        section_ids = [section.section_id for section in self.sections]
        seen: set[str] = set()
        duplicates: set[str] = set()

        for section_id in section_ids:
            if section_id in seen:
                duplicates.add(section_id)
            seen.add(section_id)

        if duplicates:
            raise ValueError(f"Duplicate section_id values are not allowed: {sorted(duplicates)}")
        return self


# -----------------------------------------------------------------------------
# Forward-reference rebuild
# -----------------------------------------------------------------------------
# TemplateDefinition references TemplateSection, while section_contracts imports
# classes from this file. We therefore rebuild the model *after* importing the
# concrete TemplateSection class into a local namespace.
try:
    from .section_contracts import TemplateSection  # pylint: disable=cyclic-import

    TemplateDefinition.model_rebuild(_types_namespace={"TemplateSection": TemplateSection})
except ImportError:
    # Safe during partial imports / early bootstrapping. The import path will be
    # fully rebuilt once section_contracts becomes available.
    pass