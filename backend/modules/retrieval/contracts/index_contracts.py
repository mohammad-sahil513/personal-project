# backend/modules/retrieval/contracts/index_contracts.py

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IndexedChunkDocument(BaseModel):
    """
    Aligned retrieval-facing indexed chunk contract.

    Mirrors the ingestion Stage 9 / Azure AI Search document shape that
    retrieval is allowed to consume.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    chunk_id: str = Field(..., description="Stable chunk identifier.")
    document_id: str = Field(..., description="Logical source document identifier.")
    section_id: str = Field(..., description="Primary hierarchy anchor for retrieval.")
    document_type: str = Field(..., description="Document type, e.g. PDD / SDD / UAT.")
    section_type: str = Field(..., description="Section taxonomy label from ingestion.")
    content: str = Field(..., description="Primary indexed chunk text.")
    summary: str | None = Field(
        default=None,
        description="Summary-backed retrieval support for section discovery.",
    )
    embedding: list[float] | None = Field(
        default=None,
        description="Vector embedding for semantic retrieval. May be omitted in projected search results.",
    )
    chunk_index_in_section: int = Field(
        ...,
        ge=0,
        description="Deterministic order of chunk inside its section.",
    )
    has_table: bool = Field(default=False, description="Whether chunk contains a table.")
    has_vision_extraction: bool = Field(
        default=False,
        description="Whether chunk contains vision-derived evidence.",
    )
    has_list: bool = Field(default=False, description="Whether chunk contains a list.")
    has_requirement_id: bool = Field(
        default=False,
        description="Broad requirement-bearing flag.",
    )
    requirement_ids: list[str] = Field(
        default_factory=list,
        description="Requirement identifiers preserved by ingestion.",
    )

    @field_validator(
        "chunk_id",
        "document_id",
        "section_id",
        "document_type",
        "section_type",
        "content",
        mode="before",
    )
    @classmethod
    def validate_non_empty_strings(cls, value: Any) -> str:
        if value is None:
            raise ValueError("Field cannot be null.")
        if not isinstance(value, str):
            raise TypeError("Field must be a string.")
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be blank.")
        return value

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("summary must be a string or null.")
        value = value.strip()
        return value or None

    @field_validator("embedding")
    @classmethod
    def validate_embedding(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if len(value) == 0:
            raise ValueError("embedding cannot be an empty list.")
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
    def sync_requirement_flag(self) -> "IndexedChunkDocument":
        if self.requirement_ids and not self.has_requirement_id:
            self.has_requirement_id = True
        return self


__all__ = ["IndexedChunkDocument"]