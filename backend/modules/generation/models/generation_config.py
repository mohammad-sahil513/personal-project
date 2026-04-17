"""
Generation module runtime configuration.

This file is the single source of truth for:
- prompt token budgets
- evidence injection caps
- rolling-context limits
- retry controls
- wave-execution defaults
- snapshot safety defaults
- diagram runtime retry limits

Important:
- Keep numeric limits centralized here.
- Do NOT duplicate these constants across prompt assembler, validators, or orchestrators.
- Keep this file configuration-only.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GenerationConfig(BaseModel):
    """
    Runtime configuration values for the Generation module.

    The defaults in this model are aligned to the approved Generation plan.
    """

    model_config = ConfigDict(extra="forbid")

    # -------------------------------------------------------------------------
    # Prompt budget controls
    # -------------------------------------------------------------------------
    max_prompt_tokens: int = Field(
        default=3000,
        ge=1,
        description="Hard upper bound for the assembled Generation prompt.",
    )

    # -------------------------------------------------------------------------
    # Evidence injection caps
    # -------------------------------------------------------------------------
    max_source_facts: int = Field(
        default=8,
        ge=1,
        description="Maximum number of SOURCE facts injected into a prompt.",
    )
    max_tables: int = Field(
        default=2,
        ge=0,
        description="Maximum number of evidence tables injected into a prompt.",
    )
    max_conflicts: int = Field(
        default=3,
        ge=0,
        description="Maximum number of conflicts injected into a prompt.",
    )

    # -------------------------------------------------------------------------
    # Rolling context controls
    # -------------------------------------------------------------------------
    max_rolling_context_sections: int = Field(
        default=2,
        ge=0,
        description="Maximum number of prior sections allowed in rolling context.",
    )
    max_rolling_context_tokens: int = Field(
        default=500,
        ge=0,
        description="Maximum total token budget for rolling context.",
    )
    max_rolling_context_tokens_per_section: int = Field(
        default=250,
        ge=0,
        description="Maximum token budget for one prior section in rolling context.",
    )

    # -------------------------------------------------------------------------
    # Validation / retry controls
    # -------------------------------------------------------------------------
    max_retries: int = Field(
        default=2,
        ge=0,
        description="Maximum number of validation-driven correction retries.",
    )

    # -------------------------------------------------------------------------
    # Snapshot safety controls
    # -------------------------------------------------------------------------
    snapshot_after_each_section: bool = Field(
        default=True,
        description="Whether Generation should persist a snapshot after each section.",
    )

    # -------------------------------------------------------------------------
    # Wave-based concurrency controls
    # -------------------------------------------------------------------------
    enable_wave_execution: bool = Field(
        default=True,
        description="Whether dependency-wave execution is enabled.",
    )
    max_parallel_sections: int = Field(
        default=3,
        ge=1,
        description="Maximum number of sections allowed to execute concurrently within a wave.",
    )

    # -------------------------------------------------------------------------
    # Diagram runtime controls
    # -------------------------------------------------------------------------
    enable_diagram_generation: bool = Field(
        default=True,
        description="Whether diagram_plantuml runtime execution is enabled.",
    )
    diagram_render_max_retries: int = Field(
        default=2,
        ge=0,
        description="Maximum number of bounded repair/render retries for diagram generation.",
    )

    # -------------------------------------------------------------------------
    # Optional behavioral flags for future-safe tuning
    # -------------------------------------------------------------------------
    preserve_source_evidence_last: bool = Field(
        default=True,
        description=(
            "When trimming prompt content under token pressure, SOURCE evidence should be preserved last."
        ),
    )
    low_evidence_min_source_facts: int = Field(
        default=2,
        ge=0,
        description=(
            "If the usable SOURCE fact count falls below this threshold, the section should be marked low-evidence/degraded."
        ),
    )


DEFAULT_GENERATION_CONFIG = GenerationConfig()

# -------------------------------------------------------------------------
# Backward-friendly exported constants for direct imports
# -------------------------------------------------------------------------
MAX_PROMPT_TOKENS = DEFAULT_GENERATION_CONFIG.max_prompt_tokens

MAX_SOURCE_FACTS = DEFAULT_GENERATION_CONFIG.max_source_facts
MAX_TABLES = DEFAULT_GENERATION_CONFIG.max_tables
MAX_CONFLICTS = DEFAULT_GENERATION_CONFIG.max_conflicts

MAX_ROLLING_CONTEXT_SECTIONS = DEFAULT_GENERATION_CONFIG.max_rolling_context_sections
MAX_ROLLING_CONTEXT_TOKENS = DEFAULT_GENERATION_CONFIG.max_rolling_context_tokens
MAX_ROLLING_CONTEXT_TOKENS_PER_SECTION = (
    DEFAULT_GENERATION_CONFIG.max_rolling_context_tokens_per_section
)

MAX_RETRIES = DEFAULT_GENERATION_CONFIG.max_retries

SNAPSHOT_AFTER_EACH_SECTION = DEFAULT_GENERATION_CONFIG.snapshot_after_each_section

ENABLE_WAVE_EXECUTION = DEFAULT_GENERATION_CONFIG.enable_wave_execution
MAX_PARALLEL_SECTIONS = DEFAULT_GENERATION_CONFIG.max_parallel_sections

ENABLE_DIAGRAM_GENERATION = DEFAULT_GENERATION_CONFIG.enable_diagram_generation
DIAGRAM_RENDER_MAX_RETRIES = DEFAULT_GENERATION_CONFIG.diagram_render_max_retries

PRESERVE_SOURCE_EVIDENCE_LAST = DEFAULT_GENERATION_CONFIG.preserve_source_evidence_last
LOW_EVIDENCE_MIN_SOURCE_FACTS = DEFAULT_GENERATION_CONFIG.low_evidence_min_source_facts