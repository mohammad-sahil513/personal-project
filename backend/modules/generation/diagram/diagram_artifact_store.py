"""
Diagram artifact store for the Generation module.

Responsibilities:
- Persist canonical PlantUML source
- Persist repaired PlantUML versions
- Persist rendered SVG / PNG artifacts
- Persist a manifest describing stored artifacts
- Return DiagramArtifactRefs for downstream assembly/export

Important:
- This file is persistence-only.
- It does NOT normalize, validate, render, repair, or embed diagrams.
- It is file/blob-artifact oriented and intentionally DB-free.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.modules.generation.contracts.generation_contracts import DiagramArtifactRefs


class DiagramArtifactStoreService:
    """
    File-based artifact store for diagram outputs.

    Storage layout under the configured base directory:

        {base_dir}/{section_id_safe}/
            source.puml
            repaired_v1.puml
            repaired_v2.puml
            render.svg
            render.png
            manifest.json
    """

    def __init__(self, base_dir: str | Path) -> None:
        base_path = Path(base_dir)
        if not str(base_path).strip():
            raise ValueError("base_dir cannot be empty.")

        self.base_dir = base_path

    def store(
        self,
        *,
        section_id: str,
        normalized_puml_text: str,
        repaired_puml_versions: list[str],
        svg_content: str | bytes | None,
        png_content: bytes | None,
        metadata: dict[str, Any] | None = None,
    ) -> DiagramArtifactRefs:
        """
        Persist diagram artifacts and return their references.

        The canonical `.puml` is always written.
        Repaired `.puml` versions are written in order when present.
        SVG/PNG are written only when provided.
        A manifest.json is always written.
        """
        if not section_id or not section_id.strip():
            raise ValueError("section_id cannot be empty.")

        if not normalized_puml_text or not normalized_puml_text.strip():
            raise ValueError("normalized_puml_text cannot be empty.")

        section_dir = self.base_dir / self._sanitize_section_id(section_id)
        section_dir.mkdir(parents=True, exist_ok=True)

        # 1) Canonical source of truth
        source_path = section_dir / "source.puml"
        source_path.write_text(normalized_puml_text, encoding="utf-8")

        # 2) Repaired versions
        repaired_paths: list[str] = []
        for idx, repaired_text in enumerate(repaired_puml_versions, start=1):
            repaired_path = section_dir / f"repaired_v{idx}.puml"
            repaired_path.write_text(repaired_text, encoding="utf-8")
            repaired_paths.append(repaired_path.as_posix())

        # 3) Render artifacts
        svg_path_str: str | None = None
        if svg_content is not None:
            svg_path = section_dir / "render.svg"
            if isinstance(svg_content, bytes):
                svg_path.write_bytes(svg_content)
            else:
                svg_path.write_text(svg_content, encoding="utf-8")
            svg_path_str = svg_path.as_posix()

        png_path_str: str | None = None
        if png_content is not None:
            png_path = section_dir / "render.png"
            png_path.write_bytes(png_content)
            png_path_str = png_path.as_posix()

        # 4) Manifest
        manifest_payload = {
            "section_id": section_id,
            "stored_at_utc": datetime.now(timezone.utc).isoformat(),
            "artifacts": {
                "source_puml": source_path.as_posix(),
                "repaired_puml_versions": repaired_paths,
                "svg": svg_path_str,
                "png": png_path_str,
            },
            "metadata": metadata or {},
        }

        manifest_path = section_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return DiagramArtifactRefs(
            puml_path=source_path.as_posix(),
            repaired_puml_paths=repaired_paths,
            svg_path=svg_path_str,
            png_path=png_path_str,
            manifest_path=manifest_path.as_posix(),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sanitize_section_id(self, section_id: str) -> str:
        """
        Convert a section_id into a filesystem-safe directory name.
        """
        value = section_id.strip()
        value = value.replace("\\", "_").replace("/", "_")
        value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
        value = value.strip("._-")
        return value or "section"