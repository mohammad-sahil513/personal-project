"""
Output route handlers.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from backend.api.dependencies import get_api_logger
from backend.application.services.output_service import OutputService
from backend.core.response import success_response

router = APIRouter(prefix="/outputs", tags=["outputs"])


@router.get("/{output_id}/download")
async def download_output(
    output_id: str,
    logger=Depends(get_api_logger),
):
    service = OutputService()

    try:
        output_dto = service.get_output(output_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Output '{output_id}' not found")

    if output_dto.status != "READY":
        raise HTTPException(
            status_code=409,
            detail=f"Output is not ready for download (status={output_dto.status})",
        )

    artifact_path = Path(output_dto.artifact_path)
    if not artifact_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Output artifact file not found on disk",
        )

    logger.info(
        "Output download requested",
        extra={"output_id": output_id, "artifact_path": str(artifact_path)},
    )

    return FileResponse(
        path=str(artifact_path),
        filename=artifact_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/{output_id}")
async def get_output_metadata(
    output_id: str,
    logger=Depends(get_api_logger),
):
    service = OutputService()

    try:
        output_dto = service.get_output(output_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Output '{output_id}' not found")

    logger.info(
        "Output metadata fetched",
        extra={"output_id": output_id},
    )

    return success_response(
        message="Output fetched successfully",
        data=output_dto.to_dict(),
    )