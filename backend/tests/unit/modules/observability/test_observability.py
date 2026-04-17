"""
Unit tests — Phase 6.2 (observability module)
Covers: PricingRegistryService, CostEstimatorService, CostAggregationService.
All tests use in-memory JSON fixtures via tmp_path — no real pricing_registry.json required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.modules.observability.services.cost_aggregation_service import (
    CostAggregationService,
    CostRecord,
    CostSummary,
)
from backend.modules.observability.services.cost_estimator_service import (
    CostEstimate,
    CostEstimatorService,
)
from backend.modules.observability.services.pricing_registry_service import (
    PricingEntry,
    PricingRegistry,
    PricingRegistryService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_REGISTRY_PAYLOAD = {
    "models": {
        "gpt-4": {
            "unit": "1k_tokens",
            "input_cost": 0.03,
            "output_cost": 0.06,
            "currency": "USD",
        },
        "gpt-35-turbo": {
            "unit": "1k_tokens",
            "input_cost": 0.0015,
            "output_cost": 0.002,
            "currency": "USD",
        },
    },
    "services": {
        "azure_search": {
            "unit": "request",
            "cost": 0.0001,
            "currency": "USD",
        },
        "azure_blob_storage": {
            "unit": "request",
            "cost": 0.00005,
            "currency": "USD",
        },
    },
}


@pytest.fixture()
def registry_path(tmp_path: Path) -> Path:
    path = tmp_path / "pricing_registry.json"
    path.write_text(json.dumps(_REGISTRY_PAYLOAD), encoding="utf-8")
    return path


@pytest.fixture()
def registry_service(registry_path: Path) -> PricingRegistryService:
    svc = PricingRegistryService(registry_path=registry_path)
    return svc


@pytest.fixture()
def estimator(registry_service: PricingRegistryService) -> CostEstimatorService:
    return CostEstimatorService(pricing_registry_service=registry_service)


@pytest.fixture()
def aggregator() -> CostAggregationService:
    return CostAggregationService()


# ---------------------------------------------------------------------------
# PricingRegistryService
# ---------------------------------------------------------------------------

class TestPricingRegistryService:
    def test_load_returns_registry(self, registry_service):
        reg = registry_service.load()
        assert isinstance(reg, PricingRegistry)
        assert "gpt-4" in reg.models

    def test_load_cached_second_call(self, registry_service):
        reg1 = registry_service.load()
        reg2 = registry_service.load()
        assert reg1 is reg2  # same object — cached

    def test_force_reload_refreshes_cache(self, registry_service):
        reg1 = registry_service.load()
        reg2 = registry_service.load(force_reload=True)
        assert reg1 is not reg2

    def test_get_model_pricing_known_model(self, registry_service):
        entry = registry_service.get_model_pricing("gpt-4")
        assert entry.input_cost == pytest.approx(0.03)
        assert entry.unit == "1k_tokens"

    def test_get_model_pricing_unknown_raises(self, registry_service):
        with pytest.raises(KeyError, match="gpt-999"):
            registry_service.get_model_pricing("gpt-999")

    def test_get_service_pricing_known_service(self, registry_service):
        entry = registry_service.get_service_pricing("azure_search")
        assert entry.cost == pytest.approx(0.0001)

    def test_get_service_pricing_unknown_raises(self, registry_service):
        with pytest.raises(KeyError):
            registry_service.get_service_pricing("nonexistent_svc")

    def test_has_model_pricing_true(self, registry_service):
        assert registry_service.has_model_pricing("gpt-4") is True

    def test_has_model_pricing_false(self, registry_service):
        assert registry_service.has_model_pricing("gpt-999") is False

    def test_has_service_pricing_true(self, registry_service):
        assert registry_service.has_service_pricing("azure_search") is True

    def test_list_models_sorted(self, registry_service):
        models = registry_service.list_models()
        assert models == sorted(models)
        assert "gpt-4" in models

    def test_list_services_sorted(self, registry_service):
        services = registry_service.list_services()
        assert services == sorted(services)

    def test_missing_registry_file_raises(self, tmp_path):
        svc = PricingRegistryService(registry_path=tmp_path / "missing.json")
        with pytest.raises(FileNotFoundError):
            svc.load()

    def test_malformed_json_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        svc = PricingRegistryService(registry_path=bad)
        with pytest.raises(ValueError, match="Invalid JSON"):
            svc.load()

    def test_empty_model_name_raises(self, registry_service):
        with pytest.raises(ValueError):
            registry_service.get_model_pricing("   ")

    def test_empty_service_name_raises(self, registry_service):
        with pytest.raises(ValueError):
            registry_service.get_service_pricing("")


# ---------------------------------------------------------------------------
# CostEstimatorService
# ---------------------------------------------------------------------------

class TestCostEstimatorService:
    def test_estimate_llm_cost_basic(self, estimator):
        # 1k prompt + 500 completion → 1.0 × 0.03 + 0.5 × 0.06 = 0.06
        result = estimator.estimate_llm_cost(
            model_name="gpt-4",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        assert isinstance(result, CostEstimate)
        assert result.amount == pytest.approx(0.03 + 0.03, rel=1e-6)

    def test_estimate_llm_cost_zero_tokens(self, estimator):
        result = estimator.estimate_llm_cost(
            model_name="gpt-4",
            prompt_tokens=0,
            completion_tokens=0,
        )
        assert result.amount == 0.0

    def test_estimate_llm_cost_metadata_passthrough(self, estimator):
        result = estimator.estimate_llm_cost(
            model_name="gpt-35-turbo",
            prompt_tokens=200,
            completion_tokens=100,
            metadata={"job_id": "j_001"},
        )
        assert result.metadata["job_id"] == "j_001"

    def test_estimate_llm_cost_negative_tokens_raises(self, estimator):
        with pytest.raises(ValueError, match="negative"):
            estimator.estimate_llm_cost(
                model_name="gpt-4",
                prompt_tokens=-10,
                completion_tokens=0,
            )

    def test_estimate_service_cost_basic(self, estimator):
        result = estimator.estimate_service_cost(
            service_name="azure_search",
            units=10.0,
        )
        assert result.amount == pytest.approx(0.001, rel=1e-6)

    def test_estimate_service_cost_zero_units(self, estimator):
        result = estimator.estimate_service_cost(
            service_name="azure_search",
            units=0.0,
        )
        assert result.amount == 0.0

    def test_estimate_service_cost_negative_units_raises(self, estimator):
        with pytest.raises(ValueError, match="negative"):
            estimator.estimate_service_cost(
                service_name="azure_search",
                units=-1,
            )

    def test_estimate_generation_section_cost_metadata(self, estimator):
        result = estimator.estimate_generation_section_cost(
            model_name="gpt-4",
            prompt_tokens=500,
            completion_tokens=200,
            section_id="sec_001",
            strategy="summarize_text",
        )
        assert result.category == "generation_section"
        assert result.metadata["section_id"] == "sec_001"
        assert result.metadata["strategy"] == "summarize_text"

    def test_estimate_diagram_section_cost_category(self, estimator):
        result = estimator.estimate_diagram_section_cost(
            model_name="gpt-4",
            prompt_tokens=300,
            completion_tokens=150,
            section_id="sec_dia",
        )
        assert result.category == "diagram_section"

    def test_currency_propagated_from_registry(self, estimator):
        result = estimator.estimate_llm_cost(
            model_name="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
        )
        assert result.currency == "USD"

    def test_units_propagated(self, estimator):
        result = estimator.estimate_llm_cost(
            model_name="gpt-4",
            prompt_tokens=2000,
            completion_tokens=1000,
        )
        assert result.input_units == pytest.approx(2.0)
        assert result.output_units == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# CostAggregationService
# ---------------------------------------------------------------------------

def _make_estimate(amount: float = 0.05, category: str = "generation_section") -> CostEstimate:
    return CostEstimate(
        category=category,
        name="gpt-4",
        unit="1k_tokens",
        amount=amount,
        currency="USD",
    )


class TestCostAggregationService:
    def test_add_and_get_record(self, aggregator):
        estimate = _make_estimate(0.05)
        record = aggregator.add_cost_record(
            job_id="job_001",
            category="generation_section",
            estimate=estimate,
        )
        assert isinstance(record, CostRecord)
        records = aggregator.get_records("job_001")
        assert len(records) == 1

    def test_empty_job_returns_empty_list(self, aggregator):
        assert aggregator.get_records("unknown_job") == []

    def test_total_cost_sum(self, aggregator):
        for amt in [0.01, 0.02, 0.03]:
            aggregator.add_cost_record(
                job_id="job_002",
                category="gen",
                estimate=_make_estimate(amt),
            )
        total = aggregator.get_total_cost("job_002")
        assert total == pytest.approx(0.06, rel=1e-6)

    def test_category_totals(self, aggregator):
        aggregator.add_cost_record(
            job_id="job_003", category="generation", estimate=_make_estimate(0.10, "generation")
        )
        aggregator.add_cost_record(
            job_id="job_003", category="search", estimate=_make_estimate(0.02, "search")
        )
        totals = aggregator.get_category_totals("job_003")
        assert totals["generation"] == pytest.approx(0.10)
        assert totals["search"] == pytest.approx(0.02)

    def test_section_totals_scoped(self, aggregator):
        aggregator.add_cost_record(
            job_id="job_004",
            category="gen",
            estimate=_make_estimate(0.05),
            section_id="sec_001",
        )
        aggregator.add_cost_record(
            job_id="job_004",
            category="gen",
            estimate=_make_estimate(0.03),
            section_id="sec_002",
        )
        aggregator.add_cost_record(
            job_id="job_004",
            category="overhead",
            estimate=_make_estimate(0.02),
            section_id=None,  # not section-scoped
        )
        totals = aggregator.get_section_totals("job_004")
        assert "sec_001" in totals
        assert "sec_002" in totals
        assert len(totals) == 2

    def test_get_summary_structure(self, aggregator):
        aggregator.add_cost_record(
            job_id="job_005", category="gen", estimate=_make_estimate(0.07), section_id="sec_a"
        )
        summary = aggregator.get_summary("job_005")
        assert isinstance(summary, CostSummary)
        assert summary.job_id == "job_005"
        assert summary.total_amount == pytest.approx(0.07)
        assert summary.record_count == 1

    def test_clear_job_removes_records(self, aggregator):
        aggregator.add_cost_record(
            job_id="job_006", category="gen", estimate=_make_estimate()
        )
        aggregator.clear_job("job_006")
        assert aggregator.get_records("job_006") == []

    def test_clear_all_empties_store(self, aggregator):
        aggregator.add_cost_record(job_id="j1", category="gen", estimate=_make_estimate())
        aggregator.add_cost_record(job_id="j2", category="gen", estimate=_make_estimate())
        aggregator.clear_all()
        assert aggregator.get_records("j1") == []
        assert aggregator.get_records("j2") == []

    def test_empty_job_id_raises(self, aggregator):
        with pytest.raises(ValueError, match="job_id"):
            aggregator.add_cost_record(job_id="", category="gen", estimate=_make_estimate())

    def test_empty_category_raises(self, aggregator):
        with pytest.raises(ValueError, match="category"):
            aggregator.add_cost_record(
                job_id="job_x", category="  ", estimate=_make_estimate()
            )

    def test_summary_empty_job(self, aggregator):
        summary = aggregator.get_summary("brand_new_job")
        assert summary.total_amount == 0.0
        assert summary.record_count == 0
