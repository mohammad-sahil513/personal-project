"""
Tests for HeuristicMapper generating section configurations.
"""

from __future__ import annotations

from pathlib import Path
import pytest
import json

from backend.modules.template.compiler.heuristic_mapper import HeuristicMapper
from backend.modules.template.contracts.compiler_contracts import (
    ExtractedDocxStructure,
    ExtractedHeading,
)

@pytest.fixture
def mock_config(tmp_path: Path) -> Path:
    # Use standard yaml mock for heuristic
    config_path = tmp_path / "heuristic_patterns.yaml"
    config_path.write_text("""
patterns:
  - section_id: executive_summary
    title: Executive Summary
    patterns:
      - executive summary
      - exec summary
  - section_id: system_diagram
    title: System Diagram
    patterns:
      - system diagram
      - architecture diagram
    """)
    return config_path


def test_heuristic_mapper_logic(mock_config: Path):
    mapper = HeuristicMapper(config_path=mock_config)
    headings = [
        ExtractedHeading(
            raw_text="Executive Summary",
            normalized_text="executive summary",
            level=1,
            order_index=0
        ),
        ExtractedHeading(
            raw_text="System Diagram",
            normalized_text="system diagram",
            level=2,
            order_index=1
        )
    ]
    
    results = mapper.map_headings(headings)
    
    assert len(results) == 2
    assert results[0].selected_section_id == "executive_summary"
    assert results[1].selected_section_id == "system_diagram"
