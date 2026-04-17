# backend/scripts/retrieval_live_smoke.py

from __future__ import annotations

import json
import os
import sys
import uuid


from backend.modules.retrieval.contracts.retrieval_contracts import (
    RetrievalFilters,
    RetrievalRequest,
)
from backend.modules.retrieval.live_wiring import build_retrieval_runtime


def main() -> int:
    runtime = build_retrieval_runtime()

    try:
        document_id = os.getenv("RETRIEVAL_SMOKE_DOCUMENT_ID")
        profile_name = os.getenv("RETRIEVAL_SMOKE_PROFILE", "default")
        section_heading = os.getenv(
            "RETRIEVAL_SMOKE_HEADING",
            "System Overview",
        )
        section_intent = os.getenv(
            "RETRIEVAL_SMOKE_INTENT",
            "Summarize the system overview and core functional behavior.",
        )
        semantic_role = os.getenv(
            "RETRIEVAL_SMOKE_ROLE",
            "overview",
        )

        filters = RetrievalFilters(document_id=document_id) if document_id else RetrievalFilters()

        request = RetrievalRequest(
            retrieval_id=f"ret_live_{uuid.uuid4().hex[:10]}",
            profile_name=profile_name,
            section_heading=section_heading,
            section_intent=section_intent,
            semantic_role=semantic_role,
            filters=filters,
        )

        evidence_bundle, diagnostics, status = runtime.retrieval_service.retrieve(request)

        result = {
            "status": status.value,
            "retrieval_id": diagnostics.retrieval_id,
            "evidence_bundle_id": diagnostics.evidence_bundle_id,
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
        }

        print(json.dumps(result, indent=2))
        return 0

    finally:
        runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
