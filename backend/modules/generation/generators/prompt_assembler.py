"""
Prompt assembler for the Generation module.

Responsibilities:
- Load prompt YAML by strategy + prompt_key
- Apply evidence caps before prompt assembly
- Apply rolling-context caps and oldest-first trimming
- Enforce hard prompt token cap
- Trim in locked order:
    1) guideline_evidence
    2) exemplar_evidence
    3) rolling_context
    4) source_evidence last

Important:
- No recency-based sorting is used.
- Evidence is selected by confidence/rerank-like score and deterministic fallback order.
- This file assembles prompts only; it does not call the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.modules.generation.contracts.generation_contracts import GenerationStrategy
from backend.modules.generation.models.generation_config import GenerationConfig, DEFAULT_GENERATION_CONFIG


# ------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------


class EvidenceTextItem(BaseModel):
    """
    Generic text evidence item used for SOURCE / GUIDELINE / EXEMPLAR evidence.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="Evidence text content.")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence or rerank-like score used for deterministic ordering.",
    )
    source_ref: str | None = Field(
        default=None,
        description="Optional stable reference such as chunk_id / fact_id / source path.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional evidence metadata.",
    )


class TableEvidenceItem(BaseModel):
    """
    Evidence table item preserved as markdown/string content.
    """

    model_config = ConfigDict(extra="forbid")

    table_markdown: str = Field(description="Markdown table or stringified table content.")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence or rerank-like score used for deterministic ordering.",
    )
    source_ref: str | None = Field(
        default=None,
        description="Optional stable reference such as chunk_id / table_id.",
    )


class ConflictEvidenceItem(BaseModel):
    """
    Conflict item used to surface contradictory evidence in a bounded way.
    """

    model_config = ConfigDict(extra="forbid")

    description: str = Field(description="Conflict summary text.")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence or severity-like score used for deterministic ordering.",
    )
    source_ref: str | None = Field(
        default=None,
        description="Optional stable reference for the conflict evidence.",
    )


class RollingContextItem(BaseModel):
    """
    Prior generated section summary used as rolling context.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Upstream section identifier.")
    section_heading: str | None = Field(default=None, description="Upstream section heading.")
    content: str = Field(description="Compressed or raw rolling-context text.")
    order_index: int = Field(
        default=0,
        ge=0,
        description="Relative ordering among prior sections. Lower is older.",
    )


class PromptAssemblyRequest(BaseModel):
    """
    Full prompt-assembly input for one target section.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Target section identifier.")
    section_heading: str = Field(description="Target section heading/title.")
    strategy: GenerationStrategy = Field(description="Resolved Generation strategy.")
    prompt_key: str = Field(description="Resolved prompt key from Template.")
    section_intent: str | None = Field(
        default=None,
        description="Optional section intent/semantic description.",
    )
    extra_instructions: str | None = Field(
        default=None,
        description="Optional section-level instructions.",
    )

    source_evidence: list[EvidenceTextItem] = Field(
        default_factory=list,
        description="Required factual grounding evidence.",
    )
    guideline_evidence: list[EvidenceTextItem] = Field(
        default_factory=list,
        description="Optional constraints / guidance evidence.",
    )
    exemplar_evidence: list[EvidenceTextItem] = Field(
        default_factory=list,
        description="Optional exemplar/reference evidence.",
    )
    table_evidence: list[TableEvidenceItem] = Field(
        default_factory=list,
        description="Optional bounded table evidence.",
    )
    conflict_evidence: list[ConflictEvidenceItem] = Field(
        default_factory=list,
        description="Optional bounded conflict evidence.",
    )
    rolling_context: list[RollingContextItem] = Field(
        default_factory=list,
        description="Optional bounded rolling context from earlier sections.",
    )

    @model_validator(mode="after")
    def validate_required_source_evidence(self) -> "PromptAssemblyRequest":
        """
        SOURCE evidence is a required slot by design.
        """
        if not self.source_evidence:
            raise ValueError("source_evidence is required and cannot be empty.")
        return self


class PromptAssemblyResult(BaseModel):
    """
    Final assembled prompt plus useful diagnostics for testing and orchestration.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_key_used: str = Field(description="Prompt key actually used after fallback resolution.")
    prompt_template_path: str = Field(description="Resolved template path used during assembly.")
    prompt_text: str = Field(description="Final assembled prompt text.")
    estimated_tokens: int = Field(ge=0, description="Estimated token count for the final prompt.")

    included_source_facts: int = Field(ge=0)
    included_guidelines: int = Field(ge=0)
    included_exemplars: int = Field(ge=0)
    included_tables: int = Field(ge=0)
    included_conflicts: int = Field(ge=0)
    included_rolling_context_sections: int = Field(ge=0)

    trimmed_guidelines: bool = Field(default=False)
    trimmed_exemplars: bool = Field(default=False)
    trimmed_rolling_context: bool = Field(default=False)
    trimmed_source_facts: bool = Field(default=False)
    used_default_prompt: bool = Field(default=False)

    warnings: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------------------
# Internal structures
# ------------------------------------------------------------------------------


@dataclass
class _ResolvedPromptTemplate:
    prompt_key_used: str
    prompt_path: Path
    template_data: dict[str, Any]
    used_default_prompt: bool


# ------------------------------------------------------------------------------
# Prompt Assembler
# ------------------------------------------------------------------------------


class PromptAssembler:
    """
    Builds the final model prompt for a section from:
    - prompt YAML
    - evidence buckets
    - rolling context
    - section metadata
    - Generation config
    """

    def __init__(
        self,
        prompts_root: Path | None = None,
        config: GenerationConfig | None = None,
    ) -> None:
        self.prompts_root = prompts_root or (Path(__file__).resolve().parents[3] / "prompts" / "generation")
        self.config = config or DEFAULT_GENERATION_CONFIG

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assemble(self, request: PromptAssemblyRequest) -> PromptAssemblyResult:
        """
        Assemble a prompt for one target section.

        High-level steps:
        1) resolve the YAML prompt template
        2) deterministically sort and cap evidence
        3) trim rolling context
        4) render prompt blocks
        5) enforce hard prompt cap with locked trimming order
        """
        resolved_template = self._load_prompt_template(
            strategy=request.strategy,
            prompt_key=request.prompt_key,
        )

        # Step 1: deterministic sort
        source_evidence = self._sort_text_evidence(request.source_evidence)
        guideline_evidence = self._sort_text_evidence(request.guideline_evidence)
        exemplar_evidence = self._sort_text_evidence(request.exemplar_evidence)
        table_evidence = self._sort_tables(request.table_evidence)
        conflict_evidence = self._sort_conflicts(request.conflict_evidence)

        # Step 2: caps before assembly
        source_evidence = source_evidence[: self.config.max_source_facts]
        table_evidence = table_evidence[: self.config.max_tables]
        conflict_evidence = conflict_evidence[: self.config.max_conflicts]

        # Step 3: rolling context oldest-first trimming, then per-section + total caps
        rolling_context = self._trim_rolling_context(request.rolling_context)

        trimmed_guidelines = False
        trimmed_exemplars = False
        trimmed_rolling_context = False
        trimmed_source_facts = False
        warnings: list[str] = []

        # Step 4: iterative prompt build + hard-cap enforcement
        while True:
            prompt_text = self._render_prompt(
                template_data=resolved_template.template_data,
                request=request,
                source_evidence=source_evidence,
                guideline_evidence=guideline_evidence,
                exemplar_evidence=exemplar_evidence,
                table_evidence=table_evidence,
                conflict_evidence=conflict_evidence,
                rolling_context=rolling_context,
            )
            estimated_tokens = self.estimate_tokens(prompt_text)

            if estimated_tokens <= self.config.max_prompt_tokens:
                break

            # Locked trim order:
            # guideline_evidence -> exemplar_evidence -> rolling_context -> source_evidence last
            if guideline_evidence:
                guideline_evidence = guideline_evidence[:-1]
                trimmed_guidelines = True
                continue

            if exemplar_evidence:
                exemplar_evidence = exemplar_evidence[:-1]
                trimmed_exemplars = True
                continue

            if rolling_context:
                rolling_context = rolling_context[1:]  # oldest already first, remove oldest first
                trimmed_rolling_context = True
                continue

            if len(source_evidence) > 1:
                source_evidence = source_evidence[:-1]
                trimmed_source_facts = True
                continue

            # Last-resort hard truncation if one source fact plus template still exceeds the cap.
            prompt_text = self._hard_truncate_to_budget(prompt_text)
            estimated_tokens = self.estimate_tokens(prompt_text)
            warnings.append("prompt_hard_truncated")
            break

        if trimmed_guidelines:
            warnings.append("guideline_evidence_trimmed")
        if trimmed_exemplars:
            warnings.append("exemplar_evidence_trimmed")
        if trimmed_rolling_context:
            warnings.append("rolling_context_trimmed")
        if trimmed_source_facts:
            warnings.append("source_evidence_trimmed_last")

        return PromptAssemblyResult(
            prompt_key_used=resolved_template.prompt_key_used,
            prompt_template_path=str(resolved_template.prompt_path),
            prompt_text=prompt_text,
            estimated_tokens=estimated_tokens,
            included_source_facts=len(source_evidence),
            included_guidelines=len(guideline_evidence),
            included_exemplars=len(exemplar_evidence),
            included_tables=len(table_evidence),
            included_conflicts=len(conflict_evidence),
            included_rolling_context_sections=len(rolling_context),
            trimmed_guidelines=trimmed_guidelines,
            trimmed_exemplars=trimmed_exemplars,
            trimmed_rolling_context=trimmed_rolling_context,
            trimmed_source_facts=trimmed_source_facts,
            used_default_prompt=resolved_template.used_default_prompt,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Template loading
    # ------------------------------------------------------------------

    def _load_prompt_template(
        self,
        strategy: GenerationStrategy,
        prompt_key: str,
    ) -> _ResolvedPromptTemplate:
        """
        Load a prompt YAML using:
        prompts/generation/{strategy}/{prompt_key}.yaml
        with fallback to default.yaml
        """
        strategy_dir = self.prompts_root / strategy.value
        specific_path = strategy_dir / f"{prompt_key}.yaml"
        default_path = strategy_dir / "default.yaml"

        if specific_path.exists():
            path = specific_path
            used_default = False
            actual_prompt_key = prompt_key
        elif default_path.exists():
            path = default_path
            used_default = True
            actual_prompt_key = "default"
        else:
            raise FileNotFoundError(
                f"No prompt template found for strategy='{strategy.value}', "
                f"prompt_key='{prompt_key}', and no default.yaml fallback exists."
            )

        with path.open("r", encoding="utf-8") as file:
            template_data = yaml.safe_load(file) or {}

        if not isinstance(template_data, dict):
            raise ValueError(f"Prompt YAML must deserialize to a mapping. Got: {type(template_data)!r}")

        return _ResolvedPromptTemplate(
            prompt_key_used=actual_prompt_key,
            prompt_path=path,
            template_data=template_data,
            used_default_prompt=used_default,
        )

    # ------------------------------------------------------------------
    # Evidence ordering
    # ------------------------------------------------------------------

    def _sort_text_evidence(self, items: list[EvidenceTextItem]) -> list[EvidenceTextItem]:
        return sorted(
            items,
            key=lambda item: (
                -item.confidence,
                item.source_ref or "",
                item.text,
            ),
        )

    def _sort_tables(self, items: list[TableEvidenceItem]) -> list[TableEvidenceItem]:
        return sorted(
            items,
            key=lambda item: (
                -item.confidence,
                item.source_ref or "",
                item.table_markdown,
            ),
        )

    def _sort_conflicts(self, items: list[ConflictEvidenceItem]) -> list[ConflictEvidenceItem]:
        return sorted(
            items,
            key=lambda item: (
                -item.confidence,
                item.source_ref or "",
                item.description,
            ),
        )

    # ------------------------------------------------------------------
    # Rolling-context trimming
    # ------------------------------------------------------------------

    def _trim_rolling_context(
        self,
        items: list[RollingContextItem],
    ) -> list[RollingContextItem]:
        """
        Apply locked rolling-context policy:
        - keep max N prior sections
        - remove oldest first if too many
        - apply per-section token cap
        - apply total token cap with oldest-first removal, then proportional truncation
        """
        if not items:
            return []

        # oldest first
        ordered = sorted(items, key=lambda item: item.order_index)

        # Keep only the most recent N sections by dropping the oldest first.
        while len(ordered) > self.config.max_rolling_context_sections:
            ordered.pop(0)

        trimmed_items: list[RollingContextItem] = []
        for item in ordered:
            trimmed_content = self._truncate_text_to_tokens(
                text=item.content,
                max_tokens=self.config.max_rolling_context_tokens_per_section,
            )
            trimmed_items.append(
                RollingContextItem(
                    section_id=item.section_id,
                    section_heading=item.section_heading,
                    content=trimmed_content,
                    order_index=item.order_index,
                )
            )

        # Enforce total rolling-context token cap
        while self._rolling_context_token_count(trimmed_items) > self.config.max_rolling_context_tokens:
            if len(trimmed_items) > 1:
                trimmed_items.pop(0)  # remove oldest section first
            else:
                # Only one section remains: truncate it proportionally
                only_item = trimmed_items[0]
                trimmed_items[0] = RollingContextItem(
                    section_id=only_item.section_id,
                    section_heading=only_item.section_heading,
                    content=self._truncate_text_to_tokens(
                        only_item.content,
                        self.config.max_rolling_context_tokens,
                    ),
                    order_index=only_item.order_index,
                )
                break

        return trimmed_items

    def _rolling_context_token_count(self, items: list[RollingContextItem]) -> int:
        return sum(self.estimate_tokens(item.content) for item in items)

    # ------------------------------------------------------------------
    # Prompt rendering
    # ------------------------------------------------------------------

    def _render_prompt(
        self,
        template_data: dict[str, Any],
        request: PromptAssemblyRequest,
        source_evidence: list[EvidenceTextItem],
        guideline_evidence: list[EvidenceTextItem],
        exemplar_evidence: list[EvidenceTextItem],
        table_evidence: list[TableEvidenceItem],
        conflict_evidence: list[ConflictEvidenceItem],
        rolling_context: list[RollingContextItem],
    ) -> str:
        """
        Render the final prompt text from YAML sections + evidence blocks.
        """
        system_text = str(template_data.get("system", "")).strip()
        instruction_text = str(template_data.get("instruction", "")).strip()
        output_contract_text = str(template_data.get("output_contract", "")).strip()
        style_notes_text = str(template_data.get("style_notes", "")).strip()

        sections: list[str] = []

        if system_text:
            sections.append(f"# SYSTEM\n{system_text}")

        sections.append("# TARGET SECTION")
        sections.append(f"Section ID: {request.section_id}")
        sections.append(f"Section Heading: {request.section_heading}")
        sections.append(f"Strategy: {request.strategy.value}")
        sections.append(f"Prompt Key: {request.prompt_key}")

        if request.section_intent:
            sections.append(f"Section Intent: {request.section_intent}")

        if instruction_text:
            sections.append(f"# INSTRUCTION\n{instruction_text}")

        if request.extra_instructions:
            sections.append(f"# EXTRA INSTRUCTIONS\n{request.extra_instructions}")

        sections.append("# SOURCE EVIDENCE")
        sections.append(self._render_text_evidence_block(source_evidence, label_prefix="SOURCE"))

        if guideline_evidence:
            sections.append("# GUIDELINE EVIDENCE")
            sections.append(self._render_text_evidence_block(guideline_evidence, label_prefix="GUIDELINE"))

        if exemplar_evidence:
            sections.append("# EXEMPLAR EVIDENCE")
            sections.append(self._render_text_evidence_block(exemplar_evidence, label_prefix="EXEMPLAR"))

        if table_evidence:
            sections.append("# TABLE EVIDENCE")
            sections.append(self._render_table_evidence_block(table_evidence))

        if conflict_evidence:
            sections.append("# CONFLICT EVIDENCE")
            sections.append(self._render_conflict_evidence_block(conflict_evidence))

        if rolling_context:
            sections.append("# ROLLING CONTEXT")
            sections.append(self._render_rolling_context_block(rolling_context))

        if output_contract_text:
            sections.append(f"# OUTPUT CONTRACT\n{output_contract_text}")

        if style_notes_text:
            sections.append(f"# STYLE NOTES\n{style_notes_text}")

        sections.append(
            "# FINAL REQUIREMENT\n"
            "Use the provided SOURCE evidence as the grounding layer. "
            "Do not invent facts beyond the supplied evidence."
        )

        return "\n\n".join(sections).strip()

    def _render_text_evidence_block(
        self,
        items: list[EvidenceTextItem],
        label_prefix: str,
    ) -> str:
        lines: list[str] = []
        for idx, item in enumerate(items, start=1):
            ref = f" [{item.source_ref}]" if item.source_ref else ""
            lines.append(f"{label_prefix} {idx}{ref}: {item.text}")
        return "\n".join(lines).strip()

    def _render_table_evidence_block(self, items: list[TableEvidenceItem]) -> str:
        lines: list[str] = []
        for idx, item in enumerate(items, start=1):
            ref = f" [{item.source_ref}]" if item.source_ref else ""
            lines.append(f"TABLE {idx}{ref}:\n{item.table_markdown}")
        return "\n\n".join(lines).strip()

    def _render_conflict_evidence_block(self, items: list[ConflictEvidenceItem]) -> str:
        lines: list[str] = []
        for idx, item in enumerate(items, start=1):
            ref = f" [{item.source_ref}]" if item.source_ref else ""
            lines.append(f"CONFLICT {idx}{ref}: {item.description}")
        return "\n".join(lines).strip()

    def _render_rolling_context_block(self, items: list[RollingContextItem]) -> str:
        lines: list[str] = []
        for idx, item in enumerate(items, start=1):
            heading = f" - {item.section_heading}" if item.section_heading else ""
            lines.append(f"CTX {idx} [{item.section_id}{heading}]: {item.content}")
        return "\n".join(lines).strip()

    # ------------------------------------------------------------------
    # Token estimation / truncation
    # ------------------------------------------------------------------

    def estimate_tokens(self, text: str) -> int:
        """
        Heuristic token estimation.

        We avoid requiring an external tokenizer dependency here.
        A simple approximation keeps prompt budgeting deterministic for tests:
        ~1 token ~= 4 characters.
        """
        if not text:
            return 0
        return ceil(len(text) / 4)

    def _truncate_text_to_tokens(self, text: str, max_tokens: int) -> str:
        """
        Truncate text to an approximate token limit using the same heuristic.
        """
        if max_tokens <= 0:
            return ""

        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip()

    def _hard_truncate_to_budget(self, text: str) -> str:
        """
        Final hard truncation if all structured trim options are exhausted.
        """
        return self._truncate_text_to_tokens(text, self.config.max_prompt_tokens)