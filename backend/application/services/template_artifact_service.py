"""
Application service for template artifact lookup and download preparation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.application.services.template_app_service import TemplateAppService
from backend.core.exceptions import NotFoundError, StorageError


class TemplateArtifactService:
    """
    Backend use-case service for locating template artifacts referenced in
    template metadata.
    """

    def __init__(
        self,
        template_app_service: TemplateAppService | None = None,
    ) -> None:
        self.template_app_service = template_app_service or TemplateAppService()

    def get_artifact(
        self,
        template_id: str,
        *,
        artifact_type: str,
    ) -> dict[str, Any]:
        """
        Resolve a template artifact by artifact type and verify its file exists.
        """
        template = self.template_app_service.get_template(template_id)

        for artifact in template.compiled_artifacts:
            if artifact.get("artifact_type") == artifact_type:
                file_path = artifact.get("file_path")
                if not file_path:
                    raise StorageError(
                        message=f"Artifact '{artifact_type}' for template '{template_id}' is missing file_path",
                        error_code="TEMPLATE_ARTIFACT_PATH_MISSING",
                        details={"template_id": template_id, "artifact_type": artifact_type},
                    )

                path_obj = Path(file_path)
                if not path_obj.exists():
                    raise NotFoundError(
                        message=f"Artifact file for '{artifact_type}' not found",
                        error_code="TEMPLATE_ARTIFACT_FILE_NOT_FOUND",
                        details={"template_id": template_id, "artifact_type": artifact_type, "file_path": file_path},
                    )

                return {
                    "template_id": template_id,
                    "artifact_type": artifact_type,
                    "name": artifact.get("name") or path_obj.name,
                    "file_path": str(path_obj),
                }

        raise NotFoundError(
            message=f"Artifact '{artifact_type}' not found for template '{template_id}'",
            error_code="TEMPLATE_ARTIFACT_NOT_FOUND",
            details={"template_id": template_id, "artifact_type": artifact_type},
        )

    def get_manifest_artifact(self, template_id: str) -> dict[str, Any]:
        return self.get_artifact(template_id, artifact_type="MANIFEST")

    def get_shell_artifact(self, template_id: str) -> dict[str, Any]:
        return self.get_artifact(template_id, artifact_type="SHELL")