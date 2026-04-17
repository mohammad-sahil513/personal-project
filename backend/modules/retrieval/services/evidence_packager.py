# backend/modules/retrieval/services/evidence_packager.py

from __future__ import annotations

import re
from itertools import combinations
from typing import Iterable

from backend.modules.retrieval.contracts.evidence_contracts import (
    ConflictEvidence,
    ConflictType,
    EvidenceBundle,
    EvidenceRef,
    FactEvidence,
    GuidelineEvidence,
    GuidelineEvidenceSet,
    SourceEvidence,
    TableEvidence,
    TableType,
)
from backend.modules.retrieval.contracts.retrieval_contracts import PoolName
from backend.modules.retrieval.repositories.search_repository import SearchCandidate


class EvidencePackager:
    """
    Convert reranked retrieval candidates into a generation-ready EvidenceBundle.

    Locked packaging behaviors implemented here:
    - per-pool deduplication
    - SOURCE precedence across duplicate pools
    - multi-fact extraction from one chunk
    - typed table extraction
    - SOURCE-only conflict detection
    - requirement ID propagation
    - evidence budget enforcement
    """

    MAX_SOURCE_FACTS = 8
    MAX_TABLES = 2
    MAX_CONFLICTS = 3
    MAX_SOURCE_REFS = 12

    @classmethod
    def package(
        cls,
        *,
        evidence_bundle_id: str,
        source_candidates: list[SearchCandidate],
        guideline_candidates: list[SearchCandidate],
        fallback_used: bool = False,
        overall_confidence: float | None = None,
    ) -> EvidenceBundle:
        # 1) per-pool dedup
        source_deduped = cls._deduplicate_by_chunk_id(source_candidates)
        guideline_deduped = cls._deduplicate_by_chunk_id(guideline_candidates)

        # 2) SOURCE precedence across duplicate pools
        source_chunk_ids = {candidate.document.chunk_id for candidate in source_deduped}
        guideline_deduped = [
            candidate
            for candidate in guideline_deduped
            if candidate.document.chunk_id not in source_chunk_ids
        ]

        # 3) refs
        source_refs = cls._build_refs(source_deduped, PoolName.SOURCE)[: cls.MAX_SOURCE_REFS]
        guideline_refs = cls._build_refs(guideline_deduped, PoolName.GUIDELINE)

        # 4) facts
        source_facts = cls._extract_source_facts(source_deduped)[: cls.MAX_SOURCE_FACTS]

        # 5) tables
        source_tables = cls._extract_source_tables(source_deduped)[: cls.MAX_TABLES]

        # 6) conflicts
        source_conflicts = cls._detect_source_conflicts(source_deduped)[: cls.MAX_CONFLICTS]

        # 7) guideline evidence
        guideline_items = cls._extract_guideline_items(guideline_deduped)

        # 8) requirement IDs (bundle-level union)
        all_requirement_ids = cls._collect_requirement_ids(
            source_deduped, guideline_deduped
        )

        # 9) confidence
        inferred_confidence = cls._infer_confidence(
            source_candidates=source_deduped,
            guideline_candidates=guideline_deduped,
        )
        final_confidence = cls._clamp_confidence(
            overall_confidence if overall_confidence is not None else inferred_confidence
        )

        source_confidence = cls._clamp_confidence(
            cls._average(
                [fact.confidence for fact in source_facts if fact.confidence is not None]
            )
        )
        guideline_confidence = cls._clamp_confidence(
            cls._average(
                [item.confidence for item in guideline_items if item.confidence is not None]
            )
        )

        source_evidence = SourceEvidence(
            facts=source_facts,
            tables=source_tables,
            conflicts=source_conflicts,
            refs=source_refs,
            confidence=source_confidence,
        )

        guideline_evidence = GuidelineEvidenceSet(
            items=guideline_items,
            refs=guideline_refs,
            confidence=guideline_confidence,
        )

        return EvidenceBundle(
            evidence_bundle_id=evidence_bundle_id,
            source=source_evidence,
            guideline=guideline_evidence,
            overall_confidence=final_confidence,
            fallback_used=fallback_used,
            requirement_ids=all_requirement_ids,
            notes=[],
        )

    # ------------------------------------------------------------------
    # Dedup / refs
    # ------------------------------------------------------------------
    @staticmethod
    def _deduplicate_by_chunk_id(
        candidates: list[SearchCandidate],
    ) -> list[SearchCandidate]:
        seen: set[str] = set()
        result: list[SearchCandidate] = []

        for candidate in candidates:
            chunk_id = candidate.document.chunk_id
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            result.append(candidate)

        return result

    @classmethod
    def _build_refs(
        cls,
        candidates: list[SearchCandidate],
        source_role: PoolName,
    ) -> list[EvidenceRef]:
        refs: list[EvidenceRef] = []

        for candidate in candidates:
            doc = candidate.document
            refs.append(
                EvidenceRef(
                    chunk_id=doc.chunk_id,
                    document_id=doc.document_id,
                    section_id=doc.section_id,
                    section_type=doc.section_type,
                    chunk_index_in_section=doc.chunk_index_in_section,
                    source_role=source_role,
                    requirement_ids=doc.requirement_ids,
                    has_table=doc.has_table,
                    has_vision_extraction=doc.has_vision_extraction,
                )
            )

        return refs

    # ------------------------------------------------------------------
    # Source fact extraction
    # ------------------------------------------------------------------
    @classmethod
    def _extract_source_facts(
        cls,
        candidates: list[SearchCandidate],
    ) -> list[FactEvidence]:
        facts: list[FactEvidence] = []
        seen_fact_texts: set[str] = set()
        fact_counter = 1

        for candidate in candidates:
            doc = candidate.document
            ref = cls._build_refs([candidate], PoolName.SOURCE)[0]

            for fact_text in cls._split_into_fact_units(doc.content):
                normalized = cls._normalize_fact_text(fact_text)
                if not normalized or normalized in seen_fact_texts:
                    continue

                seen_fact_texts.add(normalized)

                facts.append(
                    FactEvidence(
                        fact_id=f"fact_{fact_counter:03d}",
                        text=fact_text.strip(),
                        confidence=cls._candidate_confidence(candidate),
                        refs=[ref],
                        requirement_ids=doc.requirement_ids,
                        table_related=doc.has_table,
                    )
                )
                fact_counter += 1

                if len(facts) >= cls.MAX_SOURCE_FACTS:
                    return facts

        return facts

    @staticmethod
    def _split_into_fact_units(text: str) -> list[str]:
        """
        Deterministic multi-fact extraction:
        - bullet/numbered lines become separate facts
        - otherwise sentence-based split
        """
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        bullet_facts: list[str] = []

        bullet_pattern = re.compile(r"^(\-|\*|•|\d+\.)\s+")
        has_bullets = any(bullet_pattern.match(line) for line in lines)

        if has_bullets:
            for line in lines:
                if bullet_pattern.match(line):
                    cleaned = bullet_pattern.sub("", line).strip()
                    if cleaned:
                        bullet_facts.append(cleaned)
                else:
                    bullet_facts.append(line.strip())
            return bullet_facts

        sentence_parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [part.strip() for part in sentence_parts if part.strip()]

    @staticmethod
    def _normalize_fact_text(text: str) -> str:
        text = re.sub(r"\s+", " ", text.strip())
        return text.lower()

    # ------------------------------------------------------------------
    # Table extraction
    # ------------------------------------------------------------------
    @classmethod
    def _extract_source_tables(
        cls,
        candidates: list[SearchCandidate],
    ) -> list[TableEvidence]:
        tables: list[TableEvidence] = []
        table_counter = 1

        for candidate in candidates:
            doc = candidate.document
            if not doc.has_table:
                continue

            parsed_table = cls._parse_markdown_table(doc.content)
            if parsed_table is None:
                continue

            headers, rows = parsed_table
            ref = cls._build_refs([candidate], PoolName.SOURCE)[0]

            tables.append(
                TableEvidence(
                    table_id=f"table_{table_counter:03d}",
                    table_type=cls._classify_table_type(doc.section_type),
                    title=doc.summary,
                    headers=headers,
                    rows=rows,
                    refs=[ref],
                    confidence=cls._candidate_confidence(candidate),
                )
            )
            table_counter += 1

            if len(tables) >= cls.MAX_TABLES:
                return tables

        return tables

    @staticmethod
    def _parse_markdown_table(text: str) -> tuple[list[str], list[list[str]]] | None:
        """
        Parse the first markdown table found in the text.
        """
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        table_lines = [line for line in lines if "|" in line]

        if len(table_lines) < 2:
            return None

        # Find first valid header + separator pair
        for i in range(len(table_lines) - 1):
            header_line = table_lines[i]
            separator_line = table_lines[i + 1]

            if not re.fullmatch(r"\|?[\s:\-|\+]+\|?", separator_line):
                continue

            headers = [cell.strip() for cell in header_line.strip("|").split("|")]
            rows: list[list[str]] = []

            for row_line in table_lines[i + 2 :]:
                row = [cell.strip() for cell in row_line.strip("|").split("|")]
                if len(row) == len(headers):
                    rows.append(row)

            if headers and rows:
                return headers, rows

        return None

    @staticmethod
    def _classify_table_type(section_type: str) -> TableType:
        section_type_norm = section_type.strip().upper()

        if "API" in section_type_norm:
            return TableType.API_TABLE
        if "DATA" in section_type_norm or "DICTIONARY" in section_type_norm:
            return TableType.DATA_DICTIONARY
        if "MAPPING" in section_type_norm:
            return TableType.MAPPING_TABLE
        return TableType.OTHER

    # ------------------------------------------------------------------
    # Conflict detection (SOURCE-only)
    # ------------------------------------------------------------------
    @classmethod
    def _detect_source_conflicts(
        cls,
        candidates: list[SearchCandidate],
    ) -> list[ConflictEvidence]:
        conflicts: list[ConflictEvidence] = []
        conflict_counter = 1

        for left, right in combinations(candidates, 2):
            left_doc = left.document
            right_doc = right.document

            shared_requirements = set(left_doc.requirement_ids).intersection(
                right_doc.requirement_ids
            )
            if not shared_requirements:
                continue

            left_numbers = cls._extract_numbers(left_doc.content)
            right_numbers = cls._extract_numbers(right_doc.content)

            ref_left = cls._build_refs([left], PoolName.SOURCE)[0]
            ref_right = cls._build_refs([right], PoolName.SOURCE)[0]

            if left_numbers and right_numbers and left_numbers != right_numbers:
                conflicts.append(
                    ConflictEvidence(
                        conflict_id=f"conflict_{conflict_counter:03d}",
                        conflict_type=ConflictType.VALUE_MISMATCH,
                        description="Conflicting numeric values were found across SOURCE chunks sharing requirement IDs.",
                        refs=[ref_left, ref_right],
                        conflicting_values=sorted(left_numbers.union(right_numbers)),
                    )
                )
                conflict_counter += 1
            else:
                left_norm = cls._normalize_fact_text(left_doc.content)
                right_norm = cls._normalize_fact_text(right_doc.content)

                if left_norm != right_norm:
                    conflicts.append(
                        ConflictEvidence(
                            conflict_id=f"conflict_{conflict_counter:03d}",
                            conflict_type=ConflictType.TERM_MISMATCH,
                            description="Conflicting SOURCE wording was found across chunks sharing requirement IDs.",
                            refs=[ref_left, ref_right],
                            conflicting_values=[],
                        )
                    )
                    conflict_counter += 1

            if len(conflicts) >= cls.MAX_CONFLICTS:
                return conflicts

        return conflicts

    @staticmethod
    def _extract_numbers(text: str) -> set[str]:
        return set(re.findall(r"\b\d+(?:\.\d+)?\b", text))

    # ------------------------------------------------------------------
    # Guideline packaging
    # ------------------------------------------------------------------
    @classmethod
    def _extract_guideline_items(
        cls,
        candidates: list[SearchCandidate],
    ) -> list[GuidelineEvidence]:
        items: list[GuidelineEvidence] = []
        guideline_counter = 1
        seen_texts: set[str] = set()

        for candidate in candidates:
            doc = candidate.document
            ref = cls._build_refs([candidate], PoolName.GUIDELINE)[0]

            text = cls._first_guideline_unit(doc.content)
            normalized = cls._normalize_fact_text(text)
            if not normalized or normalized in seen_texts:
                continue

            seen_texts.add(normalized)

            items.append(
                GuidelineEvidence(
                    guideline_id=f"guideline_{guideline_counter:03d}",
                    text=text,
                    confidence=cls._candidate_confidence(candidate),
                    refs=[ref],
                )
            )
            guideline_counter += 1

        return items

    @classmethod
    def _first_guideline_unit(cls, text: str) -> str:
        units = cls._split_into_fact_units(text)
        return units[0] if units else text.strip()

    # ------------------------------------------------------------------
    # Confidence / requirement utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _candidate_confidence(candidate: SearchCandidate) -> float:
        if candidate.semantic_score is not None:
            return EvidencePackager._clamp_confidence(candidate.semantic_score)
        if candidate.bm25_score is not None:
            # BM25 is not naturally 0..1; treat positive values as confidence proxy and clamp.
            return EvidencePackager._clamp_confidence(candidate.bm25_score)
        return 0.0

    @staticmethod
    def _clamp_confidence(value: float | None) -> float:
        if value is None:
            return 0.0
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _average(values: Iterable[float]) -> float | None:
        values = list(values)
        if not values:
            return None
        return sum(values) / len(values)

    @classmethod
    def _infer_confidence(
        cls,
        *,
        source_candidates: list[SearchCandidate],
        guideline_candidates: list[SearchCandidate],
    ) -> float:
        values = [
            cls._candidate_confidence(candidate)
            for candidate in [*source_candidates, *guideline_candidates]
        ]
        avg = cls._average(values)
        return cls._clamp_confidence(avg)

    @staticmethod
    def _collect_requirement_ids(
        source_candidates: list[SearchCandidate],
        guideline_candidates: list[SearchCandidate],
    ) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()

        for candidate in [*source_candidates, *guideline_candidates]:
            for requirement_id in candidate.document.requirement_ids:
                if requirement_id not in seen:
                    seen.add(requirement_id)
                    ordered.append(requirement_id)

        return ordered