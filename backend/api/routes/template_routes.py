"""
Template route handlers.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse

from backend.api.dependencies import get_api_logger
from backend.api.schemas.template import TemplateCompileRequest
from backend.application.services.template_app_service import TemplateAppService
from backend.application.services.template_artifact_service import TemplateArtifactService
from backend.application.services.template_compile_service import TemplateCompileService
from backend.application.services.template_introspection_service import (
    TemplateIntrospectionService,
)
from backend.core.response import success_response
from backend.core.exceptions import ValidationError

router = APIRouter(prefix="/templates", tags=["templates"])


@router.post("/upload")
async def create_template(
    file: UploadFile = File(...),
    template_type: str | None = Form(None),
    version: str | None = Form(None),
    logger=Depends(get_api_logger),
) -> dict:
    
    if not file.filename:
        raise ValidationError("Template filename is missing.")
        
    file_bytes = await file.read()
    
    service = TemplateAppService()

    created = service.create_template(
        filename=file.filename,
        template_type=template_type,
        version=version,
        file_bytes=file_bytes
    )

    logger.info(
        "Template binary uploaded via API",
        extra={"template_id": created.template_id},
    )

    return success_response(
        message="Template uploaded successfully",
        data=created.to_dict(),
    )


@router.get("")
async def list_templates(
    logger=Depends(get_api_logger),
) -> dict:
    service = TemplateAppService()
    items = [item.to_dict() for item in service.list_templates()]

    logger.info(
        "Template list fetched",
        extra={"count": len(items)},
    )

    return success_response(
        message="Templates fetched successfully",
        data={
            "items": items,
            "total": len(items),
        },
    )


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    logger=Depends(get_api_logger),
) -> dict:
    service = TemplateAppService()
    item = service.get_template(template_id)

    logger.info(
        "Template fetched",
        extra={"template_id": template_id},
    )

    return success_response(
        message="Template fetched successfully",
        data=item.to_dict(),
    )


@router.post("/{template_id}/compile")
async def compile_template(
    template_id: str,
    payload: TemplateCompileRequest,
    background_tasks: BackgroundTasks,
    logger=Depends(get_api_logger),
) -> dict:
    _ = payload  # accepted now for forward compatibility

    service = TemplateCompileService()
    result = service.dispatch_compile(template_id, background_tasks=background_tasks)

    logger.info(
        "Template compile requested via API",
        extra={
            "template_id": template_id,
            "dispatch_mode": result.get("dispatch_mode"),
        },
    )

    return success_response(
        message="Template compilation started",
        data=result,
    )


@router.get("/{template_id}/compile-status")
async def get_template_compile_status(
    template_id: str,
    logger=Depends(get_api_logger),
) -> dict:
    service = TemplateAppService()
    item = service.get_template(template_id)

    logger.info(
        "Template compile status fetched",
        extra={"template_id": template_id, "status": item.status},
    )

    return success_response(
        message="Template compile status fetched",
        data=item.to_dict(),
    )


@router.get("/{template_id}/compiled")
async def get_compiled_template(
    template_id: str,
    logger=Depends(get_api_logger),
) -> dict:
    service = TemplateIntrospectionService()
    result = service.get_compiled_template(template_id)

    logger.info(
        "Compiled template fetched",
        extra={"template_id": template_id},
    )

    return success_response(
        message="Compiled template fetched successfully",
        data=result,
    )


@router.post("/{template_id}/validate")
async def validate_template(
    template_id: str,
    logger=Depends(get_api_logger),
) -> dict:
    service = TemplateIntrospectionService()
    result = await service.validate_template(template_id)

    logger.info(
        "Template validated via API",
        extra={"template_id": template_id, "is_valid": result["is_valid"]},
    )

    return success_response(
        message="Template validated successfully",
        data=result,
    )


@router.post("/{template_id}/resolve")
async def resolve_template(
    template_id: str,
    logger=Depends(get_api_logger),
) -> dict:
    service = TemplateIntrospectionService()
    result = await service.resolve_template(template_id)

    logger.info(
        "Template resolved via API",
        extra={"template_id": template_id, "section_count": len(result["resolved_sections"])},
    )

    return success_response(
        message="Template resolved successfully",
        data=result,
    )


@router.get("/{template_id}/manifest/download")
async def download_template_manifest(
    template_id: str,
    logger=Depends(get_api_logger),
):
    service = TemplateArtifactService()
    artifact = service.get_manifest_artifact(template_id)

    logger.info(
        "Template manifest download requested",
        extra={"template_id": template_id, "artifact_name": artifact["name"]},
    )

    return FileResponse(
        path=artifact["file_path"],
        filename=artifact["name"],
        media_type="application/octet-stream",
    )


@router.get("/{template_id}/shell/download")
async def download_template_shell(
    template_id: str,
    logger=Depends(get_api_logger),
):
    service = TemplateArtifactService()
    artifact = service.get_shell_artifact(template_id)

    logger.info(
        "Template shell download requested",
        extra={"template_id": template_id, "artifact_name": artifact["name"]},
    )

    return FileResponse(
        path=artifact["file_path"],
        filename=artifact["name"],
        media_type="application/octet-stream",
    )