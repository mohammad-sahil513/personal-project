from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class LocalArtifactStore:
    """
    Persist stage outputs locally for review.

    This is separate from logging:
    - logs skip raw content
    - artifact snapshots may contain useful stage outputs for inspection
    """

    _PROMOTED_TEXT_FIELDS = {
        "raw_markdown": "raw_markdown.md",
        "enriched_markdown": "enriched_markdown.md",
        "masked_markdown": "masked_markdown.md",
        "vision_enriched_markdown": "vision_enriched_markdown.md",
        "content": "content.txt",
        "summary": "summary.txt",
    }

    def __init__(self, *, artifacts_root: Path) -> None:
        self._artifacts_root = artifacts_root

    def store_stage_output(
        self,
        *,
        stage_name: str,
        output_model: Any,
    ) -> Path:
        stage_dir = self._artifacts_root / stage_name.lower()
        stage_dir.mkdir(parents=True, exist_ok=True)

        payload = self._normalize_output(output_model)
        json_path = stage_dir / "output.json"
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        # Promote useful text fields into human-readable files as well.
        for field_name, file_name in self._PROMOTED_TEXT_FIELDS.items():
            value = payload.get(field_name)
            if isinstance(value, str) and value.strip():
                (stage_dir / file_name).write_text(value, encoding="utf-8")

        return stage_dir

    @staticmethod
    def _normalize_output(output_model: Any) -> dict[str, Any]:
        if isinstance(output_model, BaseModel):
            return output_model.model_dump(mode="json")

        if isinstance(output_model, dict):
            return output_model

        if hasattr(output_model, "__dict__"):
            return dict(output_model.__dict__)

        return {"value": str(output_model)}