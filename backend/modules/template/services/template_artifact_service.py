"""
Template artifact persistence service.

This service is responsible for atomically persisting:
- compiled template JSON
- layout manifest
- shell DOCX
- artifact metadata

It intentionally remains file/blob-backed and DB-free.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..contracts.compiler_contracts import CompiledTemplateArtifact, CompilerArtifactReference
from ..contracts.template_contracts import TemplateDefinition
from ..layout.layout_contracts import LayoutManifest
from ..models.template_enums import CompilerArtifactType


@dataclass(frozen=True, slots=True)
class PersistedTemplateArtifacts:
    """Result of one template artifact persistence operation."""

    template_json_path: Path
    layout_manifest_path: Path | None
    shell_docx_path: Path | None
    compiled_artifact_manifest_path: Path


class TemplateArtifactService:
    """
    Persist compiled template artifacts atomically.

    Folder structure (example):
    artifacts/template/custom/<template_id>/<version>/
        ├── template.json
        ├── layout_manifest.json
        ├── shell.docx
        └── compiled_artifact.json
    """

    def __init__(self, *, artifact_root: str | Path) -> None:
        self._artifact_root = Path(artifact_root).resolve()

    def persist(
        self,
        *,
        template_definition: TemplateDefinition,
        layout_manifest: LayoutManifest | None,
        shell_docx_path: Path | None,
    ) -> PersistedTemplateArtifacts:
        """
        Persist all template artifacts in a versioned directory.
        """
        template_id = template_definition.metadata.template_id
        version = template_definition.metadata.version

        target_dir = self._artifact_root / "template" / "custom" / template_id / version
        target_dir.mkdir(parents=True, exist_ok=True)

        # -----------------------------
        # Template JSON
        # -----------------------------
        template_json_path = target_dir / "template.json"
        template_json_path.write_text(
            json.dumps(template_definition.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

        # -----------------------------
        # Layout manifest
        # -----------------------------
        layout_manifest_path: Path | None = None
        if layout_manifest is not None:
            layout_manifest_path = target_dir / "layout_manifest.json"
            layout_manifest_path.write_text(
                json.dumps(layout_manifest.model_dump(mode="json"), indent=2),
                encoding="utf-8",
            )

        # -----------------------------
        # Shell DOCX
        # -----------------------------
        persisted_shell_path: Path | None = None
        if shell_docx_path is not None:
            persisted_shell_path = target_dir / "shell.docx"
            persisted_shell_path.write_bytes(shell_docx_path.read_bytes())

        # -----------------------------
        # Compiled artifact manifest
        # -----------------------------
        compiled_artifact = CompiledTemplateArtifact(
            template_id=template_id,
            version=version,
            template_json=CompilerArtifactReference(
                artifact_type=CompilerArtifactType.COMPILED_TEMPLATE_JSON,
                path="template.json",
                version=version,
            ),
            layout_manifest=(
                CompilerArtifactReference(
                    artifact_type=CompilerArtifactType.LAYOUT_MANIFEST,
                    path="layout_manifest.json",
                    version=version,
                )
                if layout_manifest_path is not None
                else None
            ),
            shell_docx=(
                CompilerArtifactReference(
                    artifact_type=CompilerArtifactType.SHELL_DOCX,
                    path="shell.docx",
                    version=version,
                )
                if persisted_shell_path is not None
                else None
            ),
        )

        compiled_manifest_path = target_dir / "compiled_artifact.json"
        compiled_manifest_path.write_text(
            json.dumps(compiled_artifact.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

        return PersistedTemplateArtifacts(
            template_json_path=template_json_path,
            layout_manifest_path=layout_manifest_path,
            shell_docx_path=persisted_shell_path,
            compiled_artifact_manifest_path=compiled_manifest_path,
        )