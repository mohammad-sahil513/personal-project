"""
Application service for template introspection operations.
"""

from __future__ import annotations

from backend.application.services.template_app_service import TemplateAppService
from backend.application.services.template_resolve_bridge import TemplateResolveBridge
from backend.application.services.template_validation_bridge import TemplateValidationBridge


class TemplateIntrospectionService:
    """
    Backend use-case service for compiled/validate/resolve template operations.
    """

    def __init__(
        self,
        template_app_service: TemplateAppService | None = None,
        validation_bridge: TemplateValidationBridge | None = None,
        resolve_bridge: TemplateResolveBridge | None = None,
    ) -> None:
        self.template_app_service = template_app_service or TemplateAppService()
        self.validation_bridge = validation_bridge or TemplateValidationBridge()
        self.resolve_bridge = resolve_bridge or TemplateResolveBridge()

    def get_compiled_template(self, template_id: str) -> dict:
        template = self.template_app_service.get_template(template_id)

        return {
            "template_id": template.template_id,
            "filename": template.filename,
            "status": template.status,
            "compiled_artifacts": template.compiled_artifacts,
        }

    async def validate_template(self, template_id: str) -> dict:
        template = self.template_app_service.get_template(template_id)

        result = await self.validation_bridge.run_validation(
            template_id=template.template_id,
            filename=template.filename,
            template_type=template.template_type,
            version=template.version,
        )

        return {
            "template_id": template.template_id,
            "is_valid": result["is_valid"],
            "errors": result["errors"],
            "warnings": result["warnings"],
        }

    async def resolve_template(self, template_id: str) -> dict:
        template = self.template_app_service.get_template(template_id)

        result = await self.resolve_bridge.run_resolve(
            template_id=template.template_id,
            filename=template.filename,
            template_type=template.template_type,
            version=template.version,
        )

        return {
            "template_id": template.template_id,
            "resolved_sections": result["resolved_sections"],
        }