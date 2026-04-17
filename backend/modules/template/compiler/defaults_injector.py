"""
Defaults injector for deterministic custom-template compilation.

This service converts extracted headings + heuristic mapping results into a
normalized custom TemplateDefinition while applying safe defaults for:
- metadata,
- grounding policy,
- retrieval bindings,
- generation strategy,
- prompt keys,
- no-evidence policy.

Important current-sprint rule:
- the injector must never auto-assign `diagram_plantuml`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..contracts.compiler_contracts import (
    DefaultsInjectionResult,
    ExtractedHeading,
    HeuristicMappingResult,
)
from ..contracts.section_contracts import RetrievalBinding, TemplateSection
from ..contracts.template_contracts import GroundingPolicy, PromptReference, TemplateDefinition, TemplateMetadata
from ..models.template_enums import GenerationStrategy, NoEvidencePolicy, TemplateType
from .header_normalizer import HeaderNormalizer


@dataclass(frozen=True, slots=True)
class CompiledSectionSeed:
    """
    Intermediate deterministic section seed used before final defaults injection.
    """

    heading: ExtractedHeading
    selected_section_id: str | None
    selected_title: str | None
    confidence: float | None


class DefaultsInjector:
    """
    Build a normalized custom TemplateDefinition from deterministic compiler inputs.
    """

    def __init__(
        self,
        *,
        header_normalizer: HeaderNormalizer | None = None,
        default_retrieval_profile_name: str = "default_profile",
        default_grounding_policy: GroundingPolicy | None = None,
    ) -> None:
        self._header_normalizer = header_normalizer or HeaderNormalizer()
        self._default_retrieval_profile_name = default_retrieval_profile_name
        self._default_grounding_policy = default_grounding_policy or GroundingPolicy(
            strict_grounding=True,
            allow_inference=False,
            citation_required=True,
            evidence_confidence_floor=0.60,
        )

    def build_section_seeds(
        self,
        *,
        headings: list[ExtractedHeading],
        mapping_results: list[HeuristicMappingResult],
    ) -> list[CompiledSectionSeed]:
        """
        Combine headings and mapping results into deterministic section seeds.
        """
        result_by_order = {
            result.heading.order_index: result
            for result in mapping_results
        }

        seeds: list[CompiledSectionSeed] = []
        for heading in headings:
            mapping_result = result_by_order.get(heading.order_index)
            top_candidate = mapping_result.candidates[0] if mapping_result and mapping_result.candidates else None
            seeds.append(
                CompiledSectionSeed(
                    heading=heading,
                    selected_section_id=mapping_result.selected_section_id if mapping_result else None,
                    selected_title=top_candidate.title if top_candidate is not None else None,
                    confidence=top_candidate.confidence if top_candidate is not None else None,
                )
            )

        return seeds

    def inject_defaults(
        self,
        *,
        template_id: str,
        name: str,
        version: str,
        section_seeds: Iterable[CompiledSectionSeed],
        description: str | None = None,
    ) -> tuple[TemplateDefinition, DefaultsInjectionResult]:
        """
        Build a custom TemplateDefinition from deterministic section seeds.
        """
        defaults_applied: list[str] = []
        warnings: list[str] = []

        sections: list[TemplateSection] = []
        seen_section_ids: set[str] = set()

        for seed in section_seeds:
            section_id = self._ensure_unique_section_id(
                proposed_section_id=self._build_section_id(seed),
                seen_section_ids=seen_section_ids,
            )
            seen_section_ids.add(section_id)

            title = self._build_section_title(seed)
            generation_strategy = self._determine_generation_strategy(seed)
            prompt_key = self._build_prompt_key(section_id=section_id, title=title)
            retrieval = self._build_retrieval_binding(title=title)

            sections.append(
                TemplateSection(
                    section_id=section_id,
                    title=title,
                    generation_strategy=generation_strategy,
                    prompt=PromptReference(
                        prompt_key=prompt_key,
                        slot_keys=[
                            "source_evidence",
                            "exemplar_evidence",
                            "guideline_evidence",
                            "rolling_context",
                        ],
                        slots_required=["source_evidence"],
                        slots_optional=["exemplar_evidence", "guideline_evidence", "rolling_context"],
                    ),
                    retrieval=retrieval,
                    grounding_policy=self._default_grounding_policy,
                    dependencies=[],
                    no_evidence_policy=NoEvidencePolicy.DEGRADE,
                    order_hint=seed.heading.order_index,
                )
            )

            defaults_applied.extend(
                [
                    f"section_id:{section_id}",
                    f"generation_strategy:{generation_strategy.value}",
                    f"prompt_key:{prompt_key}",
                    f"retrieval_profile:{self._default_retrieval_profile_name}",
                ]
            )

            if seed.selected_section_id is None:
                warnings.append(
                    f"No deterministic heuristic match for heading `{seed.heading.raw_text}`; "
                    f"generated fallback section_id `{section_id}`."
                )

        template_definition = TemplateDefinition(
            metadata=TemplateMetadata(
                template_id=template_id,
                name=name,
                version=version,
                template_type=TemplateType.CUSTOM,
                description=description,
            ),
            default_grounding_policy=self._default_grounding_policy,
            sections=sections,
        )

        return template_definition, DefaultsInjectionResult(
            defaults_applied=defaults_applied,
            warnings=warnings,
        )

    def _build_section_id(self, seed: CompiledSectionSeed) -> str:
        """
        Determine the initial section_id for a compiled section.
        """
        if seed.selected_section_id:
            return seed.selected_section_id

        slug = self._header_normalizer.slugify(seed.heading.raw_text)
        if not slug:
            slug = f"section_{seed.heading.order_index}"

        return f"custom_{seed.heading.order_index}_{slug}"

    def _build_section_title(self, seed: CompiledSectionSeed) -> str:
        """
        Determine the display title for a compiled section.
        """
        if seed.selected_title:
            return seed.selected_title

        return seed.heading.raw_text.strip()

    def _determine_generation_strategy(self, seed: CompiledSectionSeed) -> GenerationStrategy:
        """
        Determine a safe default generation strategy.

        Rule:
        - never auto-assign `diagram_plantuml` in the current sprint,
        - use `generate_table` only for clearly tabular/document-matrix headings,
        - otherwise default to `summarize_text`.
        """
        normalized_title = seed.heading.normalized_text
        selected_section_id = seed.selected_section_id or ""

        table_indicators = {
            "data model",
            "api specification",
            "test coverage",
            "traceability",
            "matrix",
            "mapping",
            "table",
            "catalog",
        }

        if any(indicator in normalized_title for indicator in table_indicators):
            return GenerationStrategy.GENERATE_TABLE

        if any(
            indicator in selected_section_id
            for indicator in (
                "data_model",
                "api_specification",
                "test_coverage",
                "traceability",
                "matrix",
            )
        ):
            return GenerationStrategy.GENERATE_TABLE

        return GenerationStrategy.SUMMARIZE_TEXT

    def _build_prompt_key(self, *, section_id: str, title: str) -> str:
        """
        Build a prompt key that downstream prompt selection can resolve.

        Prompt selector already supports fallback to `default.yaml`, so this key
        is intentionally deterministic but not brittle.
        """
        normalized_id = section_id
        if normalized_id.startswith("sec_"):
            normalized_id = normalized_id[4:]
        elif normalized_id.startswith("custom_"):
            normalized_id = self._header_normalizer.slugify(title)

        return f"generation/{normalized_id}"

    def _build_retrieval_binding(self, *, title: str) -> RetrievalBinding:
        """
        Build a safe default retrieval binding for compiled sections.
        """
        return RetrievalBinding(
            profile_name=self._default_retrieval_profile_name,
            section_heading=title,
            section_intent=title,
            semantic_role=self._infer_semantic_role(title),
            filters={},
        )

    def _infer_semantic_role(self, title: str) -> str:
        """
        Infer a lightweight semantic role from the heading/title.
        """
        normalized = self._header_normalizer.normalize(title)

        if any(token in normalized for token in ("architecture", "component", "system overview")):
            return "architecture"
        if any(token in normalized for token in ("requirement", "scope", "acceptance")):
            return "requirements"
        if any(token in normalized for token in ("process", "workflow", "sequence", "flow")):
            return "process"
        if any(token in normalized for token in ("risk", "constraint", "assumption")):
            return "governance"

        return "general"

    @staticmethod
    def _ensure_unique_section_id(*, proposed_section_id: str, seen_section_ids: set[str]) -> str:
        """
        Ensure section IDs remain unique even for repeated fallback headings.
        """
        if proposed_section_id not in seen_section_ids:
            return proposed_section_id

        suffix = 2
        candidate = f"{proposed_section_id}_{suffix}"
        while candidate in seen_section_ids:
            suffix += 1
            candidate = f"{proposed_section_id}_{suffix}"
        return candidate