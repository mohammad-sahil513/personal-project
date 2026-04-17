"""
Template loading service.

This service sits on top of the repository and is responsible for:
- selecting the correct load path for standard vs custom templates,
- returning a typed loaded bundle,
- performing basic custom-artifact presence checks,
- emitting lightweight log messages compatible with later observability wiring.

Phase 2 intentionally limits this service to loading and artifact presence checks.
Semantic validation and resolution belong to later phases.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..contracts.compiler_contracts import CompiledTemplateArtifact
from ..contracts.template_contracts import TemplateDefinition
from ..models.template_enums import TemplateType
from ..repositories.template_repository import TemplateRepository


@dataclass(frozen=True, slots=True)
class LoadedTemplateBundle:
    """
    Loaded template artifact bundle returned by the loader service.

    Attributes:
        template_definition: Parsed and typed template definition.
        template_type: Whether the loaded template is standard or custom.
        source_path: Path to the template JSON used to build the definition.
        compiled_artifact: Compiled manifest for custom templates, otherwise None.
        layout_manifest_path: Optional resolved custom layout-manifest path.
        shell_docx_path: Optional resolved custom shell-DOCX path.
    """

    template_definition: TemplateDefinition
    template_type: TemplateType
    source_path: Path
    compiled_artifact: CompiledTemplateArtifact | None = None
    layout_manifest_path: Path | None = None
    shell_docx_path: Path | None = None


class TemplateLoaderService:
    """
    Service that loads standard or custom template artifacts.

    Logging:
        Phase 2 uses Python's standard logger interface so the implementation
        remains simple and non-invasive. Later phases can route these calls into
        the shared observability module without changing the business logic.
    """

    def __init__(
        self,
        *,
        repository: TemplateRepository,
        logger: logging.Logger | None = None,
    ) -> None:
        self._repository = repository
        self._logger = logger or logging.getLogger(__name__)

    def load_template(
        self,
        *,
        template_type: TemplateType,
        template_id: str,
        version: str | None = None,
    ) -> LoadedTemplateBundle:
        """
        Load a template by type.

        Args:
            template_type: Standard or custom.
            template_id: Template identifier.
            version: Required for custom templates.

        Returns:
            LoadedTemplateBundle with typed artifacts.

        Raises:
            ValueError: If required arguments are missing.
            FileNotFoundError: If the required artifacts do not exist.
        """
        if template_type == TemplateType.STANDARD:
            return self.load_standard_template(template_id=template_id)

        if version is None:
            raise ValueError("`version` is required when loading a custom template.")

        return self.load_custom_template(template_id=template_id, version=version)

    def load_standard_template(self, *, template_id: str) -> LoadedTemplateBundle:
        """
        Load a standard template JSON file.

        Args:
            template_id: Standard template file stem.

        Returns:
            LoadedTemplateBundle for a standard template.
        """
        self._log_info(
            "template_load_start",
            template_type=TemplateType.STANDARD.value,
            template_id=template_id,
        )

        definition = self._repository.load_standard_template(template_id)
        source_path = (
            self._repository.standard_templates_dir
            / f"{template_id}{TemplateRepository.STANDARD_TEMPLATE_FILENAME_SUFFIX}"
        ).resolve()

        bundle = LoadedTemplateBundle(
            template_definition=definition,
            template_type=TemplateType.STANDARD,
            source_path=source_path,
        )

        self._log_info(
            "template_load_completed",
            template_type=TemplateType.STANDARD.value,
            template_id=template_id,
            source_path=str(source_path),
        )
        return bundle

    def load_custom_template(
        self,
        *,
        template_id: str,
        version: str,
    ) -> LoadedTemplateBundle:
        """
        Load a custom compiled template and verify its linked artifacts.

        Args:
            template_id: Custom template identifier.
            version: Required custom template version.

        Returns:
            LoadedTemplateBundle for a custom template.

        Raises:
            FileNotFoundError: If required linked artifacts are missing.
        """
        self._log_info(
            "template_load_start",
            template_type=TemplateType.CUSTOM.value,
            template_id=template_id,
            template_version=version,
        )

        definition, artifact, source_path = self._repository.load_custom_template_definition(
            template_id=template_id,
            version=version,
        )

        manifest_dir = self._repository.custom_templates_dir / template_id / version

        layout_manifest_path = (
            self._repository.resolve_artifact_path(
                artifact_path=artifact.layout_manifest.path,
                manifest_dir=manifest_dir,
            )
            if artifact.layout_manifest is not None
            else None
        )
        shell_docx_path = (
            self._repository.resolve_artifact_path(
                artifact_path=artifact.shell_docx.path,
                manifest_dir=manifest_dir,
            )
            if artifact.shell_docx is not None
            else None
        )

        self._ensure_custom_artifacts_exist(
            template_json_path=source_path,
            layout_manifest_path=layout_manifest_path,
            shell_docx_path=shell_docx_path,
        )

        bundle = LoadedTemplateBundle(
            template_definition=definition,
            template_type=TemplateType.CUSTOM,
            source_path=source_path,
            compiled_artifact=artifact,
            layout_manifest_path=layout_manifest_path,
            shell_docx_path=shell_docx_path,
        )

        self._log_info(
            "template_load_completed",
            template_type=TemplateType.CUSTOM.value,
            template_id=template_id,
            template_version=version,
            source_path=str(source_path),
            layout_manifest_path=str(layout_manifest_path) if layout_manifest_path else None,
            shell_docx_path=str(shell_docx_path) if shell_docx_path else None,
        )
        return bundle

    @staticmethod
    def _ensure_custom_artifacts_exist(
        *,
        template_json_path: Path,
        layout_manifest_path: Path | None,
        shell_docx_path: Path | None,
    ) -> None:
        """
        Ensure required custom-template artifacts exist on disk.

        Notes:
        - template JSON is always required,
        - layout manifest and shell DOCX are optional at the contract level in
          Phase 2, but if a manifest references them, they must exist.
        """
        required_paths = [template_json_path]
        if layout_manifest_path is not None:
            required_paths.append(layout_manifest_path)
        if shell_docx_path is not None:
            required_paths.append(shell_docx_path)

        missing = [path for path in required_paths if not path.exists()]
        if missing:
            missing_display = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(f"Missing custom template artifact(s): {missing_display}")

    def _log_info(self, event_name: str, **payload: object) -> None:
        """
        Emit a lightweight structured-ish log entry.

        This keeps the loader service observable without coupling it directly to
        the shared observability module in Phase 2.
        """
        self._logger.info("%s | %s", event_name, payload)