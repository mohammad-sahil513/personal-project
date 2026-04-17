from __future__ import annotations

from typing import Any, Callable

from backend.core.exceptions import ConfigurationError


def build_template_compile_runtime_callable() -> Callable[..., Any]:
    """
    Build the default template compiler runtime callable.
    """
    try:
        from backend.modules.template.compiler.compiler_orchestrator import (
            CompilerOrchestrator,
        )
    except Exception as exc:
        raise ConfigurationError(
            message=(
                "Failed to import the template compiler runtime entrypoint. "
                "Ensure the template compiler module is available."
            ),
            error_code="TEMPLATE_RUNTIME_IMPORT_FAILED",
            details={"reason": str(exc)},
        ) from exc

    async def _runner(
        *,
        template_id: str,
        filename: str,
        template_type: str | None = None,
        version: str | None = None,
    ):
        import tempfile
        from pathlib import Path
        from backend.application.services.template_app_service import TemplateAppService

        _ = template_type

        svc = TemplateAppService()
        try:
            file_bytes = svc.get_template_bytes(template_id)
        except Exception as exc:
            raise ConfigurationError(
                message="Could not retrieve template binary for compilation.",
                error_code="TEMPLATE_BYTES_MISSING",
                details={"template_id": template_id, "error": str(exc)},
            ) from exc

        suffix = Path(filename).suffix or ".docx"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            orchestrator = CompilerOrchestrator()
            result = orchestrator.compile_custom_template(
                docx_path=tmp_path,
                template_id=template_id,
                name=filename,
                version=version or "1.0.0",
            )

            compiled_artifacts = []
            if result.template_definition:
                compiled_artifacts.append(
                    {
                        "artifact_type": "TEMPLATE_DEFINITION",
                        "name": f"{template_id}_definition.json",
                    }
                )

            return {
                "status": "COMPLETED"
                if result.semantic_validation_result.is_valid
                else "FAILED",
                "compiled_artifacts": compiled_artifacts,
                "warnings": result.correction_warnings,
                "errors": []
                if result.semantic_validation_result.is_valid
                else [
                    {
                        "code": "SEMANTIC_VALIDATION_FAILED",
                        "message": "Template failed semantic validation",
                    }
                ],
            }
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return _runner


def build_template_validation_runtime_callable() -> Callable[..., Any]:
    """
    Build the default callable for template validation.
    """
    try:
        from backend.modules.template.services.template_validator_service import (  # noqa: F401
            TemplateValidatorService,
        )
    except Exception as exc:
        raise ConfigurationError(
            message=(
                "Failed to import the template validation runtime entrypoint. "
                "Ensure the template module is available."
            ),
            error_code="TEMPLATE_VALIDATION_IMPORT_FAILED",
            details={"reason": str(exc)},
        ) from exc

    async def _runner(
        *,
        template_id: str,
        filename: str,
        template_type: str | None = None,
        version: str | None = None,
    ):
        _ = (filename, template_type, version)
        raise ConfigurationError(
            message=(
                "Template validation requires a compiled TemplateDefinition. "
                "Use the template compile endpoint first, then validate."
            ),
            error_code="TEMPLATE_VALIDATION_NOT_COMPILED",
            details={
                "template_id": template_id,
                "hint": "POST /templates/{id}/compile first, then POST /templates/{id}/validate",
            },
        )

    return _runner


def build_template_resolve_runtime_callable() -> Callable[..., Any]:
    """
    Build the default callable for template resolution.
    """
    try:
        from backend.modules.template.services.template_resolver_service import (  # noqa: F401
            TemplateResolverService,
        )
        from backend.modules.template.services.dependency_sorter_service import (  # noqa: F401
            DependencySorterService,
        )
    except Exception as exc:
        raise ConfigurationError(
            message=(
                "Failed to import the template resolve runtime entrypoint. "
                "Ensure the template module is available."
            ),
            error_code="TEMPLATE_RESOLVE_IMPORT_FAILED",
            details={"reason": str(exc)},
        ) from exc

    async def _runner(
        *,
        template_id: str,
        filename: str,
        template_type: str | None = None,
        version: str | None = None,
    ):
        _ = (filename, template_type, version)
        raise ConfigurationError(
            message=(
                "Template resolution requires a compiled TemplateDefinition. "
                "Use the template compile endpoint first, then resolve."
            ),
            error_code="TEMPLATE_RESOLVE_NOT_COMPILED",
            details={
                "template_id": template_id,
                "hint": "POST /templates/{id}/compile first, then POST /templates/{id}/resolve",
            },
        )

    return _runner
