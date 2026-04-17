"""
Application service for preparing and executing workflow output exports.
"""

from __future__ import annotations

from pathlib import Path

from backend.application.services.docx_renderer_service import DocxRendererService
from backend.application.services.output_service import OutputService
from backend.core.config import get_settings
from backend.core.exceptions import ValidationError


class OutputExportService:
    """
    Prepare and execute DOCX exports for workflows.
    """

    def __init__(
        self,
        output_service: OutputService | None = None,
        renderer: DocxRendererService | None = None,
    ) -> None:
        self.output_service = output_service or OutputService()
        self.renderer = renderer or DocxRendererService()
        self.settings = get_settings()

    def prepare_docx_export(
        self,
        *,
        workflow_run_id: str,
        assembled_document: dict,
    ) -> dict:
        """
        Create a placeholder output record for the final DOCX export.
        """
        if not assembled_document:
            raise ValidationError(
                message="assembled_document is required to prepare export",
                error_code="EXPORT_PREPARATION_INVALID",
            )

        output_dto = self.output_service.create_output(
            workflow_run_id=workflow_run_id,
            output_type="DOCUMENT",
            format="DOCX",
        )
        return output_dto.to_dict()

    def export_docx(
        self,
        *,
        output_id: str,
        workflow_run_id: str,
        assembled_document: dict,
    ) -> dict:
        if not assembled_document:
            raise ValidationError(
                message="assembled_document is required for export",
                error_code="EXPORT_INVALID",
            )

        output_path = (
            self.settings.outputs_path / workflow_run_id / f"{output_id}.docx"
        )

        artifact_path = self.renderer.render(
            assembled_document=assembled_document,
            output_path=output_path,
        )

        output = self.output_service.mark_output_ready(
            output_id,
            artifact_path=str(artifact_path),
        )

        return output.to_dict()