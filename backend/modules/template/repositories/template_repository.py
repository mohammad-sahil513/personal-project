"""
Filesystem-backed repository for template artifacts.

This repository intentionally stays aligned with the current no-DB architecture:
- standard templates are loaded from JSON files,
- custom compiled-template artifacts are stored as files plus a manifest,
- no database persistence is assumed.

Notes:
- In later phases, the same repository contract can be adapted to blob-backed
  storage if needed, while preserving the same logical interface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..contracts.compiler_contracts import CompiledTemplateArtifact
from ..contracts.template_contracts import TemplateDefinition


class TemplateRepository:
    """
    Repository responsible for reading and writing template artifacts.

    Responsibilities in Phase 2:
    - load standard template JSON files,
    - persist/load compiled custom-template manifests,
    - load custom template JSON through the manifest,
    - resolve relative artifact paths safely.
    """

    STANDARD_TEMPLATE_FILENAME_SUFFIX = ".json"
    CUSTOM_ARTIFACT_MANIFEST_FILENAME = "compiled_artifact.json"
    CUSTOM_TEMPLATE_JSON_FILENAME = "template.json"

    def __init__(
        self,
        *,
        project_root: str | Path | None = None,
        standard_templates_dir: str | Path | None = None,
        custom_templates_dir: str | Path | None = None,
    ) -> None:
        """
        Initialize repository paths.

        Args:
            project_root: Optional project-root path. If omitted, inferred from
                the repository file location.
            standard_templates_dir: Optional override for standard template files.
            custom_templates_dir: Optional override for custom compiled artifacts.
        """
        resolved_project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[4]
        )

        self._project_root = resolved_project_root
        self._standard_templates_dir = (
            Path(standard_templates_dir).resolve()
            if standard_templates_dir is not None
            else resolved_project_root / "templates" / "standard"
        )
        self._custom_templates_dir = (
            Path(custom_templates_dir).resolve()
            if custom_templates_dir is not None
            else resolved_project_root / "artifacts" / "template" / "custom"
        )

    @property
    def standard_templates_dir(self) -> Path:
        """Return the standard-templates directory."""
        return self._standard_templates_dir

    @property
    def custom_templates_dir(self) -> Path:
        """Return the custom-artifacts root directory."""
        return self._custom_templates_dir

    # ---------------------------------------------------------------------
    # Standard template operations
    # ---------------------------------------------------------------------

    def load_standard_template(self, template_id: str) -> TemplateDefinition:
        """
        Load a standard template JSON file into a typed TemplateDefinition.

        Args:
            template_id: File stem of the standard template, e.g. "pdd_v1".

        Returns:
            Parsed and validated TemplateDefinition.

        Raises:
            FileNotFoundError: If the JSON file does not exist.
            ValueError: If the JSON payload is invalid or cannot be parsed.
        """
        template_path = self._standard_templates_dir / f"{template_id}{self.STANDARD_TEMPLATE_FILENAME_SUFFIX}"
        payload = self._read_json_file(template_path)
        return TemplateDefinition.model_validate(payload)

    # ---------------------------------------------------------------------
    # Custom template operations
    # ---------------------------------------------------------------------

    def save_custom_template_definition(
        self,
        *,
        template_definition: TemplateDefinition,
        template_id: str,
        version: str,
        filename: str | None = None,
    ) -> Path:
        """
        Persist a compiled custom template definition as JSON.

        Args:
            template_definition: Typed template definition to persist.
            template_id: Logical custom template identifier.
            version: Template version string.
            filename: Optional output filename; defaults to "template.json".

        Returns:
            Path to the written template JSON file.
        """
        output_dir = self._custom_templates_dir / template_id / version
        output_dir.mkdir(parents=True, exist_ok=True)

        output_filename = filename or self.CUSTOM_TEMPLATE_JSON_FILENAME
        output_path = output_dir / output_filename

        self._write_json_file(output_path, template_definition.model_dump(mode="json"))
        return output_path

    def save_compiled_template_artifact(self, artifact: CompiledTemplateArtifact) -> Path:
        """
        Persist the compiled-artifact manifest for a custom template.

        Args:
            artifact: Manifest describing template/layout/shell artifact paths.

        Returns:
            Path to the written manifest file.
        """
        output_dir = self._custom_templates_dir / artifact.template_id / artifact.version
        output_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = output_dir / self.CUSTOM_ARTIFACT_MANIFEST_FILENAME
        self._write_json_file(manifest_path, artifact.model_dump(mode="json"))
        return manifest_path

    def load_compiled_template_artifact(
        self,
        *,
        template_id: str,
        version: str,
    ) -> CompiledTemplateArtifact:
        """
        Load a compiled-artifact manifest for a custom template.

        Args:
            template_id: Logical custom template identifier.
            version: Template version string.

        Returns:
            Parsed and validated CompiledTemplateArtifact.

        Raises:
            FileNotFoundError: If the manifest file does not exist.
            ValueError: If the manifest payload cannot be parsed/validated.
        """
        manifest_path = (
            self._custom_templates_dir
            / template_id
            / version
            / self.CUSTOM_ARTIFACT_MANIFEST_FILENAME
        )
        payload = self._read_json_file(manifest_path)
        return CompiledTemplateArtifact.model_validate(payload)

    def load_custom_template_definition(
        self,
        *,
        template_id: str,
        version: str,
    ) -> tuple[TemplateDefinition, CompiledTemplateArtifact, Path]:
        """
        Load a custom template definition together with its compiled manifest.

        Returns:
            A tuple of:
            - TemplateDefinition
            - CompiledTemplateArtifact
            - Resolved path to the template JSON file referenced by the manifest

        Raises:
            FileNotFoundError: If the manifest or template JSON is missing.
            ValueError: If the stored JSON cannot be parsed/validated.
        """
        artifact = self.load_compiled_template_artifact(template_id=template_id, version=version)
        manifest_dir = self._custom_templates_dir / template_id / version

        template_json_path = self.resolve_artifact_path(
            artifact_path=artifact.template_json.path,
            manifest_dir=manifest_dir,
        )
        payload = self._read_json_file(template_json_path)
        definition = TemplateDefinition.model_validate(payload)

        return definition, artifact, template_json_path

    def resolve_artifact_path(self, *, artifact_path: str, manifest_dir: Path) -> Path:
        """
        Resolve an artifact path from a manifest entry.

        Resolution rules:
        - absolute paths are used directly,
        - relative paths are resolved against the manifest directory.

        Args:
            artifact_path: Raw path string from the artifact manifest.
            manifest_dir: Directory containing the manifest.

        Returns:
            Resolved absolute Path.
        """
        candidate = Path(artifact_path)
        if candidate.is_absolute():
            return candidate.resolve()

        return (manifest_dir / candidate).resolve()

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------

    @staticmethod
    def _read_json_file(path: Path) -> dict[str, Any]:
        """
        Read and parse a JSON object file.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If parsing fails or root is not a JSON object.
        """
        if not path.exists():
            raise FileNotFoundError(f"Template artifact not found: {path}")

        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in template artifact: {path}") from exc

        if not isinstance(payload, dict):
            raise ValueError(f"Template artifact must contain a JSON object: {path}")

        return payload

    @staticmethod
    def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
        """Write a JSON object file with stable formatting."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")