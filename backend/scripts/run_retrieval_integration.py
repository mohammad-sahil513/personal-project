# backend/scripts/run_retrieval_integration.py

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from backend.modules.retrieval.contracts.retrieval_contracts import RetrievalFilters, RetrievalRequest
from backend.modules.retrieval.live_wiring import build_retrieval_runtime
from backend.tests.integration.retrieval.retrieval_integration_scenarios import SCENARIOS


ARTIFACT_DIR = Path("backend/artifacts/retrieval_integration")


def run_scenario(runtime, scenario):
    document_id = os.getenv(scenario.document_id_env)
    if not document_id:
        return {
            "scenario": scenario.name,
            "skipped": True,
            "reason": f"Missing environment variable: {scenario.document_id_env}",
        }

    request = RetrievalRequest(
        retrieval_id=f"ret_it_{uuid.uuid4().hex[:10]}",
        profile_name=scenario.profile_name,
        section_heading=scenario.section_heading,
        section_intent=scenario.section_intent,
        semantic_role=scenario.semantic_role,
        filters=RetrievalFilters(document_id=document_id),
    )

    evidence_bundle, diagnostics, status = runtime.retrieval_service.retrieve(request)

    return {
        "scenario": scenario.name,
        "skipped": False,
        "document_id": document_id,
        "status": status.value,
        "expected_status": scenario.expected_status.value,
        "overall_confidence": evidence_bundle.overall_confidence,
        "fallback_attempted": diagnostics.fallback_attempted,
        "warnings": [warning.value for warning in diagnostics.warnings],
        "source_fact_count": len(evidence_bundle.source.facts),
        "source_table_count": len(evidence_bundle.source.tables),
        "source_conflict_count": len(evidence_bundle.source.conflicts),
        "guideline_count": len(evidence_bundle.guideline.items),
        "requirement_ids": evidence_bundle.requirement_ids,
        "source_refs": [ref.chunk_id for ref in evidence_bundle.source.refs],
        "guideline_refs": [ref.chunk_id for ref in evidence_bundle.guideline.refs],
        "meets_min_source_facts": len(evidence_bundle.source.facts) >= scenario.min_source_facts,
        "meets_min_source_tables": len(evidence_bundle.source.tables) >= scenario.min_source_tables,
        "meets_requirement_expectation": (len(evidence_bundle.requirement_ids) > 0) if scenario.expect_requirement_ids else True,
    }


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    runtime = build_retrieval_runtime()

    try:
        results = []
        for scenario in SCENARIOS:
            result = run_scenario(runtime, scenario)
            results.append(result)

            output_path = ARTIFACT_DIR / f"{scenario.name}.json"
            output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2))

        summary_path = ARTIFACT_DIR / "summary.json"
        summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        return 0

    finally:
        runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())