"""
Application service for template compile lifecycle.
"""

from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks

from backend.application.services.template_app_service import TemplateAppService
from backend.application.services.template_runtime_bridge import TemplateRuntimeBridge
from backend.core.logging import get_logger
from backend.workers.task_dispatcher import TaskDispatcher

logger = get_logger(__name__)


class TemplateCompileService:
    """
    Backend use-case service for template compilation lifecycle.
    """

    def __init__(
        self,
        template_app_service: TemplateAppService | None = None,
        task_dispatcher: TaskDispatcher | None = None,
        template_runtime_bridge: TemplateRuntimeBridge | None = None,
    ) -> None:
        self.template_app_service = template_app_service or TemplateAppService()
        self.task_dispatcher = task_dispatcher or TaskDispatcher()
        self.template_runtime_bridge = template_runtime_bridge or TemplateRuntimeBridge()

    async def execute_compile(self, template_id: str) -> dict[str, Any]:
        """
        Execute template compilation and update metadata accordingly.
        """
        template = self.template_app_service.get_template(template_id)

        result = await self.template_runtime_bridge.run_compile(
            template_id=template.template_id,
            filename=template.filename,
            template_type=template.template_type,
            version=template.version,
        )

        status = str(result["status"]).upper()

        if status == "COMPLETED":
            updated = self.template_app_service.mark_compile_completed(
                template_id,
                compiled_artifacts=result.get("compiled_artifacts", []),
            )

            logger.info(
                "Template compilation completed",
                extra={
                    "template_id": template_id,
                    "compiled_artifact_count": len(updated.compiled_artifacts),
                },
            )

            return updated.to_dict()

        self.template_app_service.mark_compile_failed(template_id)

        logger.error(
            "Template compilation failed",
            extra={
                "template_id": template_id,
                "runtime_status": status,
                "errors": result.get("errors", []),
            },
        )

        updated = self.template_app_service.get_template(template_id)
        return updated.to_dict()

    def dispatch_compile(
        self,
        template_id: str,
        *,
        background_tasks: BackgroundTasks | None = None,
    ) -> dict[str, Any]:
        """
        Mark the template as compiling and dispatch async compile execution.
        """
        updated = self.template_app_service.mark_compile_started(template_id)

        dispatch_mode = self.task_dispatcher.dispatch(
            self.execute_compile,
            template_id,
            background_tasks=background_tasks,
        )

        logger.info(
            "Template compilation dispatched",
            extra={
                "template_id": template_id,
                "dispatch_mode": dispatch_mode,
                "compile_job_id": updated.compile_job_id,
            },
        )

        data = updated.to_dict()
        data["dispatch_mode"] = dispatch_mode
        return data