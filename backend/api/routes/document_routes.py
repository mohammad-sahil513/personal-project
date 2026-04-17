"""
Document route handlers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile, File, Form

from backend.api.dependencies import get_api_logger
from backend.application.services.document_service import DocumentService
from backend.core.response import success_response
from backend.core.exceptions import ValidationError

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def create_document(
    file: UploadFile = File(...),
    logger=Depends(get_api_logger),
) -> dict:
    
    if not file.filename:
        raise ValidationError("Filename is missing.")
        
    file_bytes = await file.read()
    
    service = DocumentService()
    created = service.create_document(
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size=len(file_bytes),
        file_bytes=file_bytes
    )

    logger.info("Document binary uploaded via API", extra={"document_id": created.document_id})

    return success_response(
        message="Document uploaded successfully",
        data=created.to_dict(),
    )


@router.get("")
async def list_documents(
    logger=Depends(get_api_logger),
) -> dict:
    service = DocumentService()
    items = [item.to_dict() for item in service.list_documents()]

    logger.info("Document list fetched", extra={"count": len(items)})

    return success_response(
        message="Documents fetched successfully",
        data={
            "items": items,
            "total": len(items),
        },
    )


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    logger=Depends(get_api_logger),
) -> dict:
    service = DocumentService()
    item = service.get_document(document_id)

    logger.info("Document fetched", extra={"document_id": document_id})

    return success_response(
        message="Document fetched successfully",
        data=item.to_dict(),
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    logger=Depends(get_api_logger),
) -> dict:
    service = DocumentService()
    deleted = service.delete_document(document_id)

    logger.info("Document deleted", extra={"document_id": document_id})

    return success_response(
        message="Document deleted successfully",
        data={
            "document_id": document_id,
            "deleted": deleted,
        },
    )