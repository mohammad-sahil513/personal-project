"""
Template module configuration constants and helper functions.

This file is the configuration source of truth for:
- allowed override keys,
- allowed filter keys,
- invalid/removed legacy filter keys,
- placeholder-compatible strategy guards.

The final aligned template plan requires:
- `final_output_top_k` support for custom template overrides,
- `section_id` as a valid filter key,
- `requirement_ids` as contract-valid but runtime-conditional,
- `diagram_plantuml` to remain placeholder-compatible for the current sprint.
"""

from __future__ import annotations

from typing import Final

from .template_enums import GenerationStrategy, PromptSlotKey

# ---------------------------------------------------------------------------
# Override semantics
# ---------------------------------------------------------------------------

STANDARD_OVERRIDE_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "min_confidence",
        "top_k",
    }
)

CUSTOM_OVERRIDE_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "min_confidence",
        "top_k",
        "final_output_top_k",
        "fallback_policy",
        "exemplar_top_k",
        "guideline_top_k",
    }
)

# ---------------------------------------------------------------------------
# Filter-key contract
# ---------------------------------------------------------------------------

ALLOWED_FILTER_KEYS: Final[frozenset[str]] = frozenset(
    {
        "chunk_id",
        "document_id",
        "section_id",
        "document_type",
        "section_type",
        "has_table",
        "has_vision_extraction",
        "has_list",
        "has_requirement_id",
        "requirement_ids",
    }
)

REMOVED_FILTER_KEYS: Final[frozenset[str]] = frozenset(
    {
        "entities",
        "actors",
        "services",
        "process_ids",
        "chunk_type",
        "graph_nodes",
        "graph_edges",
        "algorithmic_signals",
    }
)

# ---------------------------------------------------------------------------
# Strategy guardrails
# ---------------------------------------------------------------------------

UNIMPLEMENTED_STRATEGIES: Final[frozenset[str]] = frozenset(
    {
        GenerationStrategy.DIAGRAM_PLANTUML.value,
    }
)

# ---------------------------------------------------------------------------
# Prompt slot contract
# ---------------------------------------------------------------------------

REQUIRED_PROMPT_SLOTS: Final[frozenset[str]] = frozenset(
    {
        PromptSlotKey.SOURCE_EVIDENCE.value,
    }
)

OPTIONAL_PROMPT_SLOTS: Final[frozenset[str]] = frozenset(
    {
        PromptSlotKey.EXEMPLAR_EVIDENCE.value,
        PromptSlotKey.GUIDELINE_EVIDENCE.value,
        PromptSlotKey.ROLLING_CONTEXT.value,
    }
)

ALL_PROMPT_SLOTS: Final[frozenset[str]] = REQUIRED_PROMPT_SLOTS | OPTIONAL_PROMPT_SLOTS

# ---------------------------------------------------------------------------
# Runtime notes / documentation helpers
# ---------------------------------------------------------------------------

REQUIREMENT_IDS_RUNTIME_NOTE: Final[str] = (
    "The `requirement_ids` filter key is contract-valid, but runtime filtering "
    "depends on deployed Azure AI Search schema support. If support is absent, "
    "execution should degrade gracefully and may fall back to `has_requirement_id`."
)

ALIGNED_RETRIEVAL_WORDING: Final[str] = "aligned retrieval implementation"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def is_allowed_filter_key(key: str) -> bool:
    """Return True if the filter key is valid under the aligned schema contract."""
    return key in ALLOWED_FILTER_KEYS


def is_removed_filter_key(key: str) -> bool:
    """Return True if the filter key belongs to removed legacy/unsupported fields."""
    return key in REMOVED_FILTER_KEYS


def is_allowed_override_key(key: str, *, is_custom_template: bool) -> bool:
    """
    Check whether an override key is valid for the given template type.

    Args:
        key: Override field name to validate.
        is_custom_template: Whether the template is custom.

    Returns:
        True if the override is permitted for the template type.
    """
    if is_custom_template:
        return key in CUSTOM_OVERRIDE_ALLOWED_KEYS
    return key in STANDARD_OVERRIDE_ALLOWED_KEYS


def is_unimplemented_strategy(strategy: str) -> bool:
    """
    Return True if the strategy is contract-valid but intentionally not enabled
    in the current runtime scope.
    """
    return strategy in UNIMPLEMENTED_STRATEGIES
