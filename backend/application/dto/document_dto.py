"""
Application DTOs for document metadata.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class DocumentDTO:
    document_id: str
    filename: str
    content_type: str
    size: int
    uploaded_at: str
    status: str

    def to_dict(self) -> dict:
        return asdict(self)