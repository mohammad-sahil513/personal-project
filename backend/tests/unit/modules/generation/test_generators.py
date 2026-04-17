"""
Unit tests — Phase 5.2 (text_generator, table_generator)
LLM backends are mocked via deterministic protocol stubs.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from backend.modules.generation.contracts.generation_contracts import (
    GenerationStrategy,
    OutputType,
)
from backend.modules.generation.generators.text_generator import (
    TextGenerationRequest,
    TextGenerationResponse,
    TextGenerator,
    TextGenerationBackend,
)
from backend.modules.generation.generators.table_generator import (
    TableGenerationRequest,
    TableGenerationResponse,
    TableGenerator,
    TableGenerationBackend,
)


# ---------------------------------------------------------------------------
# Stub backends
# ---------------------------------------------------------------------------

class _StubTextBackend:
    """Returns a deterministic string or dict."""

    def __init__(self, response: str | dict[str, Any] = "Generated markdown content."):
        self._response = response

    def generate_text(self, prompt: str, *, model_name=None, metadata=None):
        return self._response


class _StubTableBackend:
    """Returns a deterministic markdown table string or dict."""

    _DEFAULT_TABLE = "| Col A | Col B |\n|-------|-------|\n| val1  | val2  |"

    def __init__(self, response: str | dict[str, Any] | None = None):
        self._response = response or self._DEFAULT_TABLE

    def generate_table(self, prompt: str, *, model_name=None, metadata=None):
        return self._response


def _make_text_request(**overrides) -> TextGenerationRequest:
    defaults = dict(
        section_id="sec_001",
        section_heading="System Overview",
        prompt_text="Describe the system architecture.",
        prompt_key_used="overview",
    )
    defaults.update(overrides)
    return TextGenerationRequest(**defaults)


def _make_table_request(**overrides) -> TableGenerationRequest:
    defaults = dict(
        section_id="sec_002",
        section_heading="Stages",
        prompt_text="List the pipeline stages in a table.",
        prompt_key_used="stages_table",
    )
    defaults.update(overrides)
    return TableGenerationRequest(**defaults)


# ---------------------------------------------------------------------------
# TextGenerator
# ---------------------------------------------------------------------------

class TestTextGeneratorHappyPath:
    def test_returns_text_generation_response(self):
        gen = TextGenerator(_StubTextBackend())
        resp = gen.generate(_make_text_request())
        assert isinstance(resp, TextGenerationResponse)

    def test_output_type_is_markdown_text(self):
        gen = TextGenerator(_StubTextBackend())
        resp = gen.generate(_make_text_request())
        assert resp.output.output_type == OutputType.MARKDOWN_TEXT

    def test_raw_text_in_response(self):
        gen = TextGenerator(_StubTextBackend("Hello world."))
        resp = gen.generate(_make_text_request())
        assert "Hello world" in resp.raw_text

    def test_strategy_is_summarize_text(self):
        gen = TextGenerator(_StubTextBackend())
        resp = gen.generate(_make_text_request())
        assert resp.strategy == GenerationStrategy.SUMMARIZE_TEXT

    def test_section_id_propagated(self):
        gen = TextGenerator(_StubTextBackend())
        resp = gen.generate(_make_text_request(section_id="custom_sec"))
        assert resp.section_id == "custom_sec"

    def test_dict_backend_response_extracts_text(self):
        gen = TextGenerator(_StubTextBackend({"text": "Dict-backed content.", "model": "gpt-4"}))
        resp = gen.generate(_make_text_request())
        assert "Dict-backed content" in resp.raw_text
        assert resp.backend_metadata.get("model") == "gpt-4"

    def test_fenced_markdown_unwrapped(self):
        fenced = "```markdown\n## Section\n\nContent inside fence.\n```"
        gen = TextGenerator(_StubTextBackend(fenced))
        resp = gen.generate(_make_text_request())
        assert not resp.raw_text.startswith("```")
        assert "Content inside fence" in resp.raw_text

    def test_plain_fenced_triple_backtick_unwrapped(self):
        fenced = "```\nPlain content.\n```"
        gen = TextGenerator(_StubTextBackend(fenced))
        resp = gen.generate(_make_text_request())
        assert resp.raw_text.strip() == "Plain content."


class TestTextGeneratorEdgeCases:
    def test_empty_backend_response_raises(self):
        gen = TextGenerator(_StubTextBackend("   "))
        with pytest.raises(ValueError, match="empty"):
            gen.generate(_make_text_request())

    def test_empty_prompt_text_raises_validation(self):
        with pytest.raises(ValidationError):
            _make_text_request(prompt_text="   ")

    def test_dict_backend_missing_text_field_raises(self):
        gen = TextGenerator(_StubTextBackend({"no_text": "wrong"}))
        with pytest.raises(ValueError, match="string `text` field"):
            gen.generate(_make_text_request())

    def test_invalid_backend_type_raises(self):
        with pytest.raises(TypeError, match="protocol"):
            TextGenerator("not a backend")  # type: ignore


# ---------------------------------------------------------------------------
# TableGenerator
# ---------------------------------------------------------------------------

class TestTableGeneratorHappyPath:
    def test_returns_table_generation_response(self):
        gen = TableGenerator(_StubTableBackend())
        resp = gen.generate(_make_table_request())
        assert isinstance(resp, TableGenerationResponse)

    def test_output_type_is_markdown_table(self):
        gen = TableGenerator(_StubTableBackend())
        resp = gen.generate(_make_table_request())
        assert resp.output.output_type == OutputType.MARKDOWN_TABLE

    def test_raw_table_markdown_returned(self):
        gen = TableGenerator(_StubTableBackend())
        resp = gen.generate(_make_table_request())
        assert "Col A" in resp.raw_table_markdown

    def test_strategy_is_generate_table(self):
        gen = TableGenerator(_StubTableBackend())
        resp = gen.generate(_make_table_request())
        assert resp.strategy == GenerationStrategy.GENERATE_TABLE

    def test_dict_backend_response_extracts_text(self):
        gen = TableGenerator(_StubTableBackend({"text": "| H |\n|---|\n| v |", "tokens": 12}))
        resp = gen.generate(_make_table_request())
        assert "| H |" in resp.raw_table_markdown
        assert resp.backend_metadata.get("tokens") == 12

    def test_fenced_table_block_unwrapped(self):
        fenced = "```\n| Col |\n|-----|\n| v   |\n```"
        gen = TableGenerator(_StubTableBackend(fenced))
        resp = gen.generate(_make_table_request())
        assert not resp.raw_table_markdown.startswith("```")


class TestTableGeneratorEdgeCases:
    def test_empty_backend_response_raises(self):
        gen = TableGenerator(_StubTableBackend("   "))
        with pytest.raises(ValueError, match="empty"):
            gen.generate(_make_table_request())

    def test_invalid_backend_type_raises(self):
        with pytest.raises(TypeError, match="protocol"):
            TableGenerator(object())  # type: ignore
