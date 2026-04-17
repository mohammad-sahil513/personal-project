"""
Integration test — Phase 5 Generation Module.
Chains: PromptAssembler → TextGenerator (stub) → OutputValidator → SectionAssembler → TOCGenerator
using in-memory mocks. No LLM, no file I/O beyond a temp prompt root.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.modules.generation.assembly.section_assembler import (
    SectionAssembler,
    SectionAssemblyRequest,
)
from backend.modules.generation.assembly.toc_generator import (
    TOCGenerationRequest,
    TOCGenerator,
)
from backend.modules.generation.contracts.generation_contracts import (
    GenerationStrategy,
    OutputType,
    SectionExecutionStatus,
    SectionGenerationResult,
    SectionOutput,
)
from backend.modules.generation.generators.prompt_assembler import (
    EvidenceTextItem,
    PromptAssembler,
    PromptAssemblyRequest,
    RollingContextItem,
)
from backend.modules.generation.generators.text_generator import (
    TextGenerationRequest,
    TextGenerator,
)
from backend.modules.generation.models.generation_config import GenerationConfig
from backend.modules.generation.validators.output_validator import (
    OutputValidationRequest,
    OutputValidationRules,
    OutputValidator,
    ValidationIssueCode,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def prompt_root(tmp_path: Path) -> Path:
    """
    Create a minimal on-disk prompt template tree for PromptAssembler.
    Strategy dir: summarize_text / default.yaml
    """
    strategy_dir = tmp_path / "summarize_text"
    strategy_dir.mkdir(parents=True)
    default_yaml = strategy_dir / "default.yaml"
    default_yaml.write_text(
        textwrap.dedent("""\
            system: "You are an expert technical writer."
            instruction: "Write a factual, concise section based on the provided evidence."
            output_contract: "Return clean markdown text only."
            style_notes: "Use ## headings. Do not use tables here."
        """),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def assembler(prompt_root: Path) -> PromptAssembler:
    config = GenerationConfig(max_prompt_tokens=2000, max_source_facts=4)
    return PromptAssembler(prompts_root=prompt_root, config=config)


class _StubTextBackend:
    """Deterministic stub — ignores token budget and always returns valid markdown."""

    def generate_text(self, prompt: str, *, model_name=None, metadata=None) -> str:
        return (
            "## System Overview\n\n"
            "The AI SDLC Engine automates documentation generation for enterprise pipelines. "
            "It ingests PDF and DOCX source documents, extracts structured evidence, "
            "and generates SDLC artefacts using a modular retrieval-augmented approach."
        )


@pytest.fixture()
def text_generator() -> TextGenerator:
    return TextGenerator(_StubTextBackend())


@pytest.fixture()
def validator() -> OutputValidator:
    return OutputValidator()


@pytest.fixture()
def section_assembler() -> SectionAssembler:
    return SectionAssembler()


@pytest.fixture()
def toc_generator() -> TOCGenerator:
    return TOCGenerator()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _source_fact(text: str, confidence: float = 0.85) -> EvidenceTextItem:
    return EvidenceTextItem(text=text, confidence=confidence)


def _assembly_request(prompt_root: Path) -> PromptAssemblyRequest:
    return PromptAssemblyRequest(
        section_id="sec_overview",
        section_heading="System Overview",
        strategy=GenerationStrategy.SUMMARIZE_TEXT,
        prompt_key="overview",
        section_intent="Describe the high-level architecture of the AI SDLC Engine.",
        source_evidence=[
            _source_fact("The AI SDLC Engine automates documentation workflows."),
            _source_fact("The engine supports PDF and DOCX ingestion formats."),
        ],
        guideline_evidence=[
            EvidenceTextItem(text="All outputs must comply with GDPR data handling requirements.", confidence=0.70),
        ],
    )


# ---------------------------------------------------------------------------
# Step 1 — PromptAssembler
# ---------------------------------------------------------------------------

class TestPromptAssemblerIntegration:
    def test_assembles_valid_prompt(self, assembler, prompt_root):
        req = _assembly_request(prompt_root)
        result = assembler.assemble(req)
        assert result.prompt_text.strip() != ""
        assert result.included_source_facts == 2

    def test_prompt_contains_source_evidence(self, assembler, prompt_root):
        req = _assembly_request(prompt_root)
        result = assembler.assemble(req)
        assert "SOURCE" in result.prompt_text

    def test_prompt_contains_guideline_evidence(self, assembler, prompt_root):
        req = _assembly_request(prompt_root)
        result = assembler.assemble(req)
        assert "GUIDELINE" in result.prompt_text

    def test_prompt_contains_system_block(self, assembler, prompt_root):
        req = _assembly_request(prompt_root)
        result = assembler.assemble(req)
        assert "SYSTEM" in result.prompt_text

    def test_token_count_within_budget(self, assembler, prompt_root):
        req = _assembly_request(prompt_root)
        result = assembler.assemble(req)
        assert result.estimated_tokens <= 2000

    def test_uses_default_prompt_for_unknown_key(self, assembler, prompt_root):
        req = PromptAssemblyRequest(
            section_id="sec_custom",
            section_heading="Custom Section",
            strategy=GenerationStrategy.SUMMARIZE_TEXT,
            prompt_key="nonexistent_custom_key",
            source_evidence=[_source_fact("Some fact.")],
        )
        result = assembler.assemble(req)
        assert result.used_default_prompt is True

    def test_rolling_context_included(self, assembler, prompt_root):
        req = PromptAssemblyRequest(
            section_id="sec_002",
            section_heading="Security",
            strategy=GenerationStrategy.SUMMARIZE_TEXT,
            prompt_key="default",
            source_evidence=[_source_fact("Security fact here.")],
            rolling_context=[
                RollingContextItem(
                    section_id="sec_001",
                    section_heading="Overview",
                    content="The system overview was generated previously.",
                    order_index=0,
                )
            ],
        )
        result = assembler.assemble(req)
        assert "ROLLING CONTEXT" in result.prompt_text
        assert result.included_rolling_context_sections == 1

    def test_token_budget_trims_guideline_first(self, prompt_root):
        """With a very tight budget, guidelines should be trimmed before source evidence."""
        tight_config = GenerationConfig(max_prompt_tokens=100, max_source_facts=2)
        tight_assembler = PromptAssembler(prompts_root=prompt_root, config=tight_config)
        req = PromptAssemblyRequest(
            section_id="sec_tight",
            section_heading="Tight Section",
            strategy=GenerationStrategy.SUMMARIZE_TEXT,
            prompt_key="default",
            source_evidence=[
                _source_fact("Source fact A."),
                _source_fact("Source fact B."),
            ],
            guideline_evidence=[
                EvidenceTextItem(text=" ".join(["word"] * 100), confidence=0.5),
            ],
        )
        result = tight_assembler.assemble(req)
        # Guidelines should be trimmed
        assert result.trimmed_guidelines is True
        # Source must still be present (last to be trimmed)
        assert result.included_source_facts >= 1


# ---------------------------------------------------------------------------
# Step 2 — Full pipeline: Assemble → Generate → Validate → Assemble sections
# ---------------------------------------------------------------------------

class TestGenerationPipelineIntegration:
    def test_end_to_end_produces_valid_section_result(
        self, assembler, text_generator, validator, section_assembler, toc_generator, prompt_root
    ):
        # Step A: Assemble prompt
        prompt_result = assembler.assemble(_assembly_request(prompt_root))
        assert prompt_result.prompt_text.strip() != ""

        # Step B: Generate text
        gen_request = TextGenerationRequest(
            section_id="sec_overview",
            section_heading="System Overview",
            prompt_text=prompt_result.prompt_text,
            prompt_key_used=prompt_result.prompt_key_used,
        )
        gen_response = text_generator.generate(gen_request)
        assert gen_response.output.output_type == OutputType.MARKDOWN_TEXT

        # Step C: Validate output
        val_result = validator.validate(
            OutputValidationRequest(
                section_id="sec_overview",
                strategy=GenerationStrategy.SUMMARIZE_TEXT,
                output=gen_response.output,
                rules=OutputValidationRules(min_words=5),
            )
        )
        assert val_result.is_valid is True
        assert val_result.word_count > 5

        # Step D: Build SectionGenerationResult
        section_result = SectionGenerationResult(
            section_id="sec_overview",
            section_heading="System Overview",
            strategy=GenerationStrategy.SUMMARIZE_TEXT,
            status=SectionExecutionStatus.GENERATED,
            output=gen_response.output,
        )

        # Step E: Assemble sections
        assembly = section_assembler.assemble(
            SectionAssemblyRequest(
                ordered_section_ids=["sec_overview"],
                section_results=[section_result],
            )
        )
        assert assembly.included_section_count == 1
        assert "System Overview" in assembly.assembled_markdown or \
               "AI SDLC Engine" in assembly.assembled_markdown

        # Step F: Generate TOC
        toc = toc_generator.generate(
            TOCGenerationRequest(assembled_sections=assembly.assembled_sections)
        )
        assert toc.included_entry_count == 1
        assert "System Overview" in toc.toc_markdown

    def test_multi_section_pipeline_preserves_order(
        self, assembler, text_generator, validator, section_assembler, toc_generator, prompt_root
    ):
        results = []
        section_ids = ["sec_overview", "sec_security", "sec_architecture"]
        headings = ["Overview", "Security", "Architecture"]

        for section_id, heading in zip(section_ids, headings):
            prompt_result = assembler.assemble(
                PromptAssemblyRequest(
                    section_id=section_id,
                    section_heading=heading,
                    strategy=GenerationStrategy.SUMMARIZE_TEXT,
                    prompt_key="default",
                    source_evidence=[_source_fact(f"{heading} related fact.")],
                )
            )
            gen_response = text_generator.generate(
                TextGenerationRequest(
                    section_id=section_id,
                    section_heading=heading,
                    prompt_text=prompt_result.prompt_text,
                    prompt_key_used=prompt_result.prompt_key_used,
                )
            )
            results.append(
                SectionGenerationResult(
                    section_id=section_id,
                    section_heading=heading,
                    strategy=GenerationStrategy.SUMMARIZE_TEXT,
                    status=SectionExecutionStatus.GENERATED,
                    output=gen_response.output,
                )
            )

        assembly = section_assembler.assemble(
            SectionAssemblyRequest(
                ordered_section_ids=section_ids,
                section_results=results,
            )
        )
        assert assembly.included_section_count == 3
        assembled_ids = [s.section_id for s in assembly.assembled_sections]
        assert assembled_ids == section_ids

        toc = toc_generator.generate(
            TOCGenerationRequest(assembled_sections=assembly.assembled_sections)
        )
        assert toc.included_entry_count == 3
