# backend/modules/retrieval/contracts/evidence_contracts.py

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .retrieval_contracts import PoolName


class TableType(str, Enum):
    API_TABLE = "api_table"
    DATA_DICTIONARY = "data_dictionary"
    MAPPING_TABLE = "mapping_table"
    OTHER = "other"


class ConflictType(str, Enum):
    VALUE_MISMATCH = "value_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"
    TERM_MISMATCH = "term_mismatch"


class EvidenceRef(BaseModel):
    """
    Trace reference back to indexed evidence.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    chunk_id: str
    document_id: str
    section_id: str
    section_type: str | None = None
    chunk_index_in_section: int | None = Field(default=None, ge=0)
    source_role: PoolName
    requirement_ids: list[str] = Field(default_factory=list)
    has_table: bool = False
    has_vision_extraction: bool = False

    @field_validator("chunk_id", "document_id", "section_id", "section_type", mode="before")
    @classmethod
    def normalize_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("Value must be a string or null.")
        value = value.strip()
        return value or None

    @field_validator("requirement_ids", mode="before")
    @classmethod
    def normalize_requirement_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("requirement_ids must be a list of strings.")

        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if item is None:
                continue
            if not isinstance(item, str):
                raise TypeError("Each requirement_id must be a string.")
            item = item.strip()
            if not item:
                continue
            if item not in seen:
                seen.add(item)
                normalized.append(item)
        return normalized


class FactEvidence(BaseModel):
    """
    One factual evidence statement. One chunk may yield multiple facts.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    fact_id: str
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    refs: list[EvidenceRef] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)
    table_related: bool = False

    @field_validator("fact_id", "text", mode="before")
    @classmethod
    def normalize_required_strings(cls, value: Any) -> str:
        if value is None:
            raise ValueError("Field cannot be null.")
        if not isinstance(value, str):
            raise TypeError("Field must be a string.")
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be blank.")
        return value

    @field_validator("requirement_ids", mode="before")
    @classmethod
    def normalize_requirement_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("requirement_ids must be a list of strings.")

        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if item is None:
                continue
            if not isinstance(item, str):
                raise TypeError("Each requirement_id must be a string.")
            item = item.strip()
            if not item:
                continue
            if item not in seen:
                seen.add(item)
                normalized.append(item)
        return normalized

    @model_validator(mode="after")
    def ensure_refs_present(self) -> "FactEvidence":
        if not self.refs:
            raise ValueError("FactEvidence must include at least one evidence reference.")
        return self


class GuidelineEvidence(BaseModel):
    """
    Guideline/constraint/reference evidence item.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    guideline_id: str
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    refs: list[EvidenceRef] = Field(default_factory=list)

    @field_validator("guideline_id", "text", mode="before")
    @classmethod
    def normalize_required_strings(cls, value: Any) -> str:
        if value is None:
            raise ValueError("Field cannot be null.")
        if not isinstance(value, str):
            raise TypeError("Field must be a string.")
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be blank.")
        return value

    @model_validator(mode="after")
    def ensure_refs_present(self) -> "GuidelineEvidence":
        if not self.refs:
            raise ValueError("GuidelineEvidence must include at least one evidence reference.")
        return self


class TableEvidence(BaseModel):
    """
    Structured table evidence extracted from a chunk.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    table_id: str
    table_type: TableType = TableType.OTHER
    title: str | None = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    refs: list[EvidenceRef] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("table_id", "title", mode="before")
    @classmethod
    def normalize_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("Value must be a string or null.")
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_table_shape(self) -> "TableEvidence":
        if not self.table_id:
            raise ValueError("table_id cannot be blank.")
        if not self.refs:
            raise ValueError("TableEvidence must include at least one evidence reference.")
        if self.headers:
            expected_columns = len(self.headers)
            for row in self.rows:
                if len(row) != expected_columns:
                    raise ValueError(
                        "Each table row must match the number of headers."
                    )
        return self


class ConflictEvidence(BaseModel):
    """
    SOURCE-only conflict identified during evidence packaging.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    conflict_id: str
    conflict_type: ConflictType
    description: str
    refs: list[EvidenceRef] = Field(default_factory=list)
    conflicting_values: list[str] = Field(default_factory=list)

    @field_validator("conflict_id", "description", mode="before")
    @classmethod
    def normalize_required_strings(cls, value: Any) -> str:
        if value is None:
            raise ValueError("Field cannot be null.")
        if not isinstance(value, str):
            raise TypeError("Field must be a string.")
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be blank.")
        return value

    @field_validator("conflicting_values", mode="before")
    @classmethod
    def normalize_conflicting_values(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("conflicting_values must be a list of strings.")
        cleaned: list[str] = []
        for item in value:
            if item is None:
                continue
            if not isinstance(item, str):
                raise TypeError("Each conflicting value must be a string.")
            item = item.strip()
            if item:
                cleaned.append(item)
        return cleaned

    @model_validator(mode="after")
    def validate_source_only_refs(self) -> "ConflictEvidence":
        if not self.refs:
            raise ValueError("ConflictEvidence must include at least one evidence reference.")
        if any(ref.source_role != PoolName.SOURCE for ref in self.refs):
            raise ValueError("ConflictEvidence refs must all belong to SOURCE.")
        return self


class SourceEvidence(BaseModel):
    """
    SOURCE evidence slot for factual grounding.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    facts: list[FactEvidence] = Field(default_factory=list)
    tables: list[TableEvidence] = Field(default_factory=list)
    conflicts: list[ConflictEvidence] = Field(default_factory=list)
    refs: list[EvidenceRef] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_refs_are_source(self) -> "SourceEvidence":
        if any(ref.source_role != PoolName.SOURCE for ref in self.refs):
            raise ValueError("All SourceEvidence refs must belong to SOURCE.")
        return self


class GuidelineEvidenceSet(BaseModel):
    """
    GUIDELINE evidence slot for constraints/reference guidance.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    items: list[GuidelineEvidence] = Field(default_factory=list)
    refs: list[EvidenceRef] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_refs_are_guideline(self) -> "GuidelineEvidenceSet":
        if any(ref.source_role != PoolName.GUIDELINE for ref in self.refs):
            raise ValueError("All GuidelineEvidenceSet refs must belong to GUIDELINE.")
        return self


class EvidenceBundle(BaseModel):
    """
    Final generation-facing retrieval output bundle.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    evidence_bundle_id: str
    source: SourceEvidence = Field(default_factory=SourceEvidence)
    guideline: GuidelineEvidenceSet = Field(default_factory=GuidelineEvidenceSet)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    fallback_used: bool = False
    requirement_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("evidence_bundle_id")
    @classmethod
    def validate_bundle_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("evidence_bundle_id cannot be blank.")
        return value

    @field_validator("requirement_ids", mode="before")
    @classmethod
    def normalize_requirement_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("requirement_ids must be a list of strings.")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if item is None:
                continue
            if not isinstance(item, str):
                raise TypeError("Each requirement_id must be a string.")
            item = item.strip()
            if not item:
                continue
            if item not in seen:
                seen.add(item)
                normalized.append(item)
        return normalized


__all__ = [
    "TableType",
    "ConflictType",
    "EvidenceRef",
    "FactEvidence",
    "GuidelineEvidence",
    "TableEvidence",
    "ConflictEvidence",
    "SourceEvidence",
    "GuidelineEvidenceSet",
    "EvidenceBundle",
]