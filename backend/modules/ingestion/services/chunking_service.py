"""
Chunking service for Stage 8.

This service performs deterministic, retrieval-aligned chunking:
- chunk by segmented section
- preserve atomic blocks such as tables, code fences, lists, and vision blocks
- extract requirement IDs
- assign chunk_index_in_section
- generate summaries with guaranteed per-section summary coverage
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from time import perf_counter

from backend.modules.ingestion.contracts.stage_1_contracts import StageWarning
from backend.modules.ingestion.contracts.stage_8_contracts import (
    ChunkWarning,
    ChunkWarningCode,
    EnrichedChunk,
    Stage8Input,
    Stage8Metrics,
    Stage8Output,
)
from backend.modules.ingestion.exceptions import ChunkingError


@dataclass
class _Block:
    """Internal representation of a section content block."""

    text: str
    block_type: str
    estimated_tokens: int


class ChunkingService:
    """Service that executes deterministic semantic chunking for Stage 8."""

    _WORD_PATTERN = re.compile(r"\S+")
    _REQUIREMENT_ID_PATTERN = re.compile(
        r"\b(?:REQ|FR|NFR|BR|US|STORY|R)[-_ ]?\d+\b",
        re.IGNORECASE,
    )
    _VISION_BLOCK_PATTERN = re.compile(r"\[VISION_EXTRACTED:.*?\]", re.DOTALL | re.IGNORECASE)
    _TABLE_LINE_PATTERN = re.compile(r"^\s*\|.+\|\s*$")
    _LIST_LINE_PATTERN = re.compile(r"^\s*(?:[-*+]\s+|\d+\.\s+).+")
    _CODE_FENCE_PATTERN = re.compile(r"^```")

    def chunk_document(self, request: Stage8Input) -> Stage8Output:
        """Create retrieval-aligned chunks from segmented sections."""
        if not request.validation_summary.can_proceed_to_chunking:
            raise ChunkingError(
                "Stage 8 cannot proceed because Stage 7 validation reported global failure.",
                context={
                    "document_id": request.document_id,
                    "error_count": request.validation_summary.error_count,
                },
            )

        start_time = perf_counter()

        all_chunks: list[EnrichedChunk] = []
        all_warnings: list[StageWarning] = list(request.prior_warnings)

        sections_with_forced_summary = 0
        merged_fragment_count = 0
        forced_split_count = 0

        for section in request.sections:
            section_blocks = self._extract_atomic_blocks(section.raw_content)
            section_chunks, section_forced_summary, section_merge_count, section_forced_splits = (
                self._chunk_single_section(
                    document_id=request.document_id,
                    section_id=section.section_id,
                    section_type=section.section_type.value,
                    blocks=section_blocks,
                    section_token_hint=section.structural_signals.estimated_tokens,
                )
            )

            sections_with_forced_summary += int(section_forced_summary)
            merged_fragment_count += section_merge_count
            forced_split_count += section_forced_splits

            all_chunks.extend(section_chunks)

            for chunk in section_chunks:
                for warning in chunk.chunk_warnings:
                    all_warnings.append(
                        StageWarning(
                            code=warning.code.value,
                            message=warning.message,
                            details={
                                "section_id": warning.section_id,
                                "chunk_id": warning.chunk_id,
                                **warning.details,
                            },
                        )
                    )

        total_duration_ms = (perf_counter() - start_time) * 1000
        metrics = Stage8Metrics(
            total_sections_processed=len(request.sections),
            total_chunks_created=len(all_chunks),
            sections_with_forced_summary=sections_with_forced_summary,
            merged_fragment_count=merged_fragment_count,
            forced_split_count=forced_split_count,
            total_duration_ms=round(total_duration_ms, 3),
        )

        return Stage8Output(
            process_id=request.process_id,
            document_id=request.document_id,
            source_blob=request.source_blob,
            chunks=all_chunks,
            warnings=all_warnings,
            metrics=metrics,
        )

    def _chunk_single_section(
        self,
        *,
        document_id: str,
        section_id: str,
        section_type: str,
        blocks: list[_Block],
        section_token_hint: int,
    ) -> tuple[list[EnrichedChunk], bool, int, int]:
        """
        Chunk a single section deterministically.

        Returns:
        - list of chunks
        - whether section summary was forced
        - merged fragment count
        - forced split count
        """
        if not blocks:
            raise ChunkingError(
                "Section cannot be chunked because it contains no usable blocks.",
                context={"section_id": section_id},
            )

        target_max_tokens = 700 if self._is_structure_heavy(blocks) else 800
        target_min_tokens = 100

        provisional_chunks: list[list[_Block]] = []
        current_blocks: list[_Block] = []
        current_tokens = 0
        forced_split_count = 0

        for block in blocks:
            # If a single atomic block is too large, either keep it as-is with warnings
            # or split only if it is plain prose.
            if block.estimated_tokens > target_max_tokens:
                if current_blocks:
                    provisional_chunks.append(current_blocks)
                    current_blocks = []
                    current_tokens = 0

                if block.block_type in {"table", "vision", "code", "list"}:
                    provisional_chunks.append([block])
                else:
                    split_blocks = self._split_large_prose_block(block, target_max_tokens)
                    forced_split_count += max(0, len(split_blocks) - 1)
                    provisional_chunks.extend([[split_block] for split_block in split_blocks])
                continue

            if current_tokens + block.estimated_tokens > target_max_tokens and current_blocks:
                provisional_chunks.append(current_blocks)
                current_blocks = [block]
                current_tokens = block.estimated_tokens
            else:
                current_blocks.append(block)
                current_tokens += block.estimated_tokens

        if current_blocks:
            provisional_chunks.append(current_blocks)

        merged_fragment_count = 0
        merged_chunks = self._merge_tiny_fragments(
            provisional_chunks=provisional_chunks,
            target_min_tokens=target_min_tokens,
        )
        merged_fragment_count = max(0, len(provisional_chunks) - len(merged_chunks))

        chunk_models: list[EnrichedChunk] = []
        summary_present = False

        for chunk_index, block_group in enumerate(merged_chunks):
            content = "\n\n".join(block.text.strip() for block in block_group if block.text.strip()).strip()
            estimated_tokens = self._estimate_tokens(content)

            requirement_ids = self._extract_requirement_ids(content)
            has_requirement_pattern = bool(self._REQUIREMENT_ID_PATTERN.search(content))
            chunk_warnings: list[ChunkWarning] = []

            if estimated_tokens > target_max_tokens:
                warning_code = (
                    ChunkWarningCode.OVERSIZED_TABLE_CHUNK
                    if self._contains_table(content)
                    else ChunkWarningCode.OVERSIZED_CHUNK
                )
                chunk_warnings.append(
                    ChunkWarning(
                        code=warning_code,
                        message="Chunk exceeds the recommended token target but was preserved to keep atomic structure intact.",
                        section_id=section_id,
                        details={"estimated_tokens": estimated_tokens},
                    )
                )

            if has_requirement_pattern and not requirement_ids:
                chunk_warnings.append(
                    ChunkWarning(
                        code=ChunkWarningCode.REQUIREMENT_IDS_EXTRACTED_EMPTY,
                        message="Chunk appears to contain requirement-like structure but no explicit requirement IDs were extracted.",
                        section_id=section_id,
                        details={},
                    )
                )

            summary = self._generate_summary_if_needed(content, estimated_tokens)
            if summary is None:
                chunk_warnings.append(
                    ChunkWarning(
                        code=ChunkWarningCode.SUMMARY_SKIPPED,
                        message="Chunk summary was skipped because the chunk is short and structurally simple.",
                        section_id=section_id,
                        details={"estimated_tokens": estimated_tokens},
                    )
                )
            else:
                summary_present = True

            chunk_id = f"{section_id}_chunk_{chunk_index:03d}"

            # Attach chunk_id after it is created so warnings can reference it.
            for warning in chunk_warnings:
                warning.chunk_id = chunk_id

            chunk_models.append(
                EnrichedChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    section_id=section_id,
                    section_type=section_type,
                    chunk_index_in_section=chunk_index,
                    content=content,
                    summary=summary,
                    estimated_tokens=estimated_tokens,
                    has_table=self._contains_table(content),
                    has_vision_extraction=bool(self._VISION_BLOCK_PATTERN.search(content)),
                    has_list=self._contains_list(content),
                    has_requirement_id=bool(requirement_ids),
                    requirement_ids=requirement_ids,
                    chunk_warnings=chunk_warnings,
                )
            )

        forced_summary = False
        if chunk_models and not summary_present:
            forced_summary = True
            representative_summary = self._generate_section_level_summary(
                section_id=section_id,
                chunk_contents=[chunk.content for chunk in chunk_models],
            )
            chunk_models[0].summary = representative_summary
            chunk_models[0].chunk_warnings.append(
                ChunkWarning(
                    code=ChunkWarningCode.SECTION_SUMMARY_FORCED,
                    message="Section had no natural summary candidate, so a representative section summary was attached to the first chunk.",
                    section_id=section_id,
                    chunk_id=chunk_models[0].chunk_id,
                    details={},
                )
            )

        return chunk_models, forced_summary, merged_fragment_count, forced_split_count

    def _extract_atomic_blocks(self, raw_content: str) -> list[_Block]:
        """Extract deterministic content blocks while preserving atomic structures."""
        lines = raw_content.splitlines()
        blocks: list[_Block] = []
        buffer: list[str] = []

        def flush_paragraph_buffer() -> None:
            if not buffer:
                return
            paragraph_text = "\n".join(buffer).strip()
            if paragraph_text:
                blocks.append(
                    _Block(
                        text=paragraph_text,
                        block_type="paragraph",
                        estimated_tokens=self._estimate_tokens(paragraph_text),
                    )
                )
            buffer.clear()

        index = 0
        while index < len(lines):
            line = lines[index]

            if not line.strip():
                flush_paragraph_buffer()
                index += 1
                continue

            if self._CODE_FENCE_PATTERN.match(line.strip()):
                flush_paragraph_buffer()
                code_lines = [line]
                index += 1
                while index < len(lines):
                    code_lines.append(lines[index])
                    if self._CODE_FENCE_PATTERN.match(lines[index].strip()):
                        index += 1
                        break
                    index += 1
                block_text = "\n".join(code_lines).strip()
                blocks.append(_Block(block_text, "code", self._estimate_tokens(block_text)))
                continue

            if self._VISION_BLOCK_PATTERN.search(line):
                flush_paragraph_buffer()
                block_text = line.strip()
                blocks.append(_Block(block_text, "vision", self._estimate_tokens(block_text)))
                index += 1
                continue

            if self._TABLE_LINE_PATTERN.match(line):
                flush_paragraph_buffer()
                table_lines = [line]
                index += 1
                while index < len(lines) and self._TABLE_LINE_PATTERN.match(lines[index]):
                    table_lines.append(lines[index])
                    index += 1
                block_text = "\n".join(table_lines).strip()
                blocks.append(_Block(block_text, "table", self._estimate_tokens(block_text)))
                continue

            if self._LIST_LINE_PATTERN.match(line):
                flush_paragraph_buffer()
                list_lines = [line]
                index += 1
                while index < len(lines):
                    next_line = lines[index]
                    if self._LIST_LINE_PATTERN.match(next_line) or next_line.startswith("  "):
                        list_lines.append(next_line)
                        index += 1
                    else:
                        break
                block_text = "\n".join(list_lines).strip()
                blocks.append(_Block(block_text, "list", self._estimate_tokens(block_text)))
                continue

            buffer.append(line)
            index += 1

        flush_paragraph_buffer()

        return self._apply_attachment_rules(blocks)

    def _apply_attachment_rules(self, blocks: list[_Block]) -> list[_Block]:
        """
        Keep heading + first content block together when possible.

        This implements the locked attachment rule in a deterministic way without
        requiring an LLM or deep semantic parsing.
        """
        if len(blocks) < 2:
            return blocks

        first_block = blocks[0]
        second_block = blocks[1]

        if first_block.text.lstrip().startswith("#"):
            attached_text = f"{first_block.text.strip()}\n\n{second_block.text.strip()}".strip()
            attached_block = _Block(
                text=attached_text,
                block_type="paragraph",
                estimated_tokens=self._estimate_tokens(attached_text),
            )
            return [attached_block, *blocks[2:]]

        return blocks

    def _split_large_prose_block(self, block: _Block, target_max_tokens: int) -> list[_Block]:
        """Fallback-split a large prose block by sentence-like boundaries."""
        sentences = re.split(r"(?<=[.!?])\s+", block.text.strip())
        if len(sentences) <= 1:
            return [block]

        split_blocks: list[_Block] = []
        current_sentences: list[str] = []
        current_tokens = 0

        for sentence in sentences:
            sentence_tokens = self._estimate_tokens(sentence)
            if current_tokens + sentence_tokens > target_max_tokens and current_sentences:
                text = " ".join(current_sentences).strip()
                split_blocks.append(_Block(text, "paragraph", self._estimate_tokens(text)))
                current_sentences = [sentence]
                current_tokens = sentence_tokens
            else:
                current_sentences.append(sentence)
                current_tokens += sentence_tokens

        if current_sentences:
            text = " ".join(current_sentences).strip()
            split_blocks.append(_Block(text, "paragraph", self._estimate_tokens(text)))

        return split_blocks or [block]

    def _merge_tiny_fragments(
        self,
        *,
        provisional_chunks: list[list[_Block]],
        target_min_tokens: int,
    ) -> list[list[_Block]]:
        """Merge small chunk fragments into the previous chunk when safe."""
        if not provisional_chunks:
            return []

        merged: list[list[_Block]] = [provisional_chunks[0]]

        for chunk_blocks in provisional_chunks[1:]:
            chunk_tokens = sum(block.estimated_tokens for block in chunk_blocks)
            if chunk_tokens < target_min_tokens:
                merged[-1].extend(chunk_blocks)
            else:
                merged.append(chunk_blocks)

        return merged

    def _generate_summary_if_needed(self, content: str, estimated_tokens: int) -> str | None:
        """
        Generate a deterministic summary when the chunk is large/complex enough.

        Locked rule:
        - long/complex/tabular chunks => summary
        - short clean chunks may skip summary
        """
        if estimated_tokens < 150 and not self._contains_table(content) and not self._contains_list(content):
            return None

        plain_text = re.sub(r"(?m)^#+\s*", "", content).strip()
        plain_text = re.sub(r"\s+", " ", plain_text)

        if len(plain_text) <= 220:
            return plain_text

        return plain_text[:217].rstrip() + "..."

    def _generate_section_level_summary(self, *, section_id: str, chunk_contents: list[str]) -> str:
        """
        Generate a deterministic representative summary for an entire section.

        This is used only when no chunk in the section naturally received a summary.
        """
        combined = " ".join(re.sub(r"\s+", " ", content).strip() for content in chunk_contents).strip()
        combined = re.sub(r"(?m)^#+\s*", "", combined)

        if len(combined) <= 220:
            return combined

        return combined[:217].rstrip() + "..."

    def _extract_requirement_ids(self, content: str) -> list[str]:
        """Extract unique requirement IDs while preserving order."""
        seen: set[str] = set()
        ordered_ids: list[str] = []

        for match in self._REQUIREMENT_ID_PATTERN.finditer(content):
            normalized = re.sub(r"\s+", "", match.group(0).upper())
            if normalized not in seen:
                seen.add(normalized)
                ordered_ids.append(normalized)

        return ordered_ids

    def _is_structure_heavy(self, blocks: list[_Block]) -> bool:
        """Return True if the section contains structure-heavy content."""
        return any(block.block_type in {"table", "list", "vision", "code"} for block in blocks)

    def _contains_table(self, content: str) -> bool:
        return any(self._TABLE_LINE_PATTERN.match(line) for line in content.splitlines())

    def _contains_list(self, content: str) -> bool:
        return any(self._LIST_LINE_PATTERN.match(line) for line in content.splitlines())

    def _estimate_tokens(self, text: str) -> int:
        word_count = len(self._WORD_PATTERN.findall(text))
        return max(1, round(word_count * 1.3))