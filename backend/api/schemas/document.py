"""
API schema models for document routes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentCreateResponseData(BaseModel):
    document_id: str
    filename: str
    content_type: str
    size: int
    uploaded_at: str
    status: str


class DocumentDetailResponseData(BaseModel):
    document_id: str
    filename: str
    content_type: str
    size: int
    uploaded_at: str
    status: str


class DocumentListResponseData(BaseModel):
    items: list[DocumentDetailResponseData]
    total: int


class DocumentDeleteResponseData(BaseModel):
    document_id: str
    deleted: bool


class DocumentUploadRequestInfo(BaseModel):
    """
    Optional auxiliary request metadata model if needed later.
    """
    document_type: str | None = Field(default=None)
    notes: str | None = Field(default=None)