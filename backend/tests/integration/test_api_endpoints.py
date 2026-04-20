"""
Integration tests — Phase 6.4b (API Routes)
Covers the FastAPI route surface area. Mocks application services to isolate HTTP testing.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.router import api_router
from backend.application.dto.document_dto import DocumentDTO
from backend.application.dto.output_dto import OutputDTO
from backend.application.dto.template_dto import TemplateDTO
from backend.application.dto.workflow_dto import WorkflowDTO
from backend.core.config import get_settings


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(api_router)
    # The routers have no prefixes except api_prefix on api_router, 
    # but the settings.api_prefix is usually "/api/v1". We will patch that out 
    # or just use it. It's safe to just use the routers.
    from backend.api.error_handlers import register_exception_handlers
    register_exception_handlers(app)
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


# ---------------------------------------------------------------------------
# Health Routes
# ---------------------------------------------------------------------------
def test_health_check(client):
    settings = get_settings()
    url = f"{settings.api_prefix}/health"
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["status"] == "ok"


def test_readiness_check(client):
    settings = get_settings()
    url = f"{settings.api_prefix}/ready"
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "status" in response.json()["data"]


# ---------------------------------------------------------------------------
# Document Routes
# ---------------------------------------------------------------------------
@patch("backend.api.routes.document_routes.DocumentService")
def test_list_documents(MockDocService, client):
    mock_instance = MockDocService.return_value
    mock_instance.list_documents.return_value = [
        DocumentDTO("doc_1", "test.pdf", "application/pdf", 100, "now", "AVAILABLE")
    ]
    
    settings = get_settings()
    url = f"{settings.api_prefix}/documents"
    response = client.get(url)
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["document_id"] == "doc_1"


@patch("backend.api.routes.document_routes.DocumentService")
def test_upload_document(MockDocService, client):
    mock_instance = MockDocService.return_value
    mock_instance.create_document.return_value = DocumentDTO(
        "doc_2", "empty.txt", "text/plain", 12, "now", "AVAILABLE"
    )
    
    settings = get_settings()
    url = f"{settings.api_prefix}/documents/upload"
    files = {"file": ("empty.txt", b"Hello world!", "text/plain")}
    response = client.post(url, files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["document_id"] == "doc_2"
    mock_instance.create_document.assert_called_once()


# ---------------------------------------------------------------------------
# Template Routes
# ---------------------------------------------------------------------------
@patch("backend.api.routes.template_routes.TemplateAppService")
def test_get_template(MockTplService, client):
    mock_instance = MockTplService.return_value
    mock_instance.get_template.return_value = TemplateDTO(
        "tpl_1", "t.docx", "SDLC", "1.0", "ACTIVE", "now", "now"
    )
    
    settings = get_settings()
    url = f"{settings.api_prefix}/templates/tpl_1"
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["data"]["template_id"] == "tpl_1"


# ---------------------------------------------------------------------------
# Workflow Routes
# ---------------------------------------------------------------------------
@patch("backend.api.routes.workflow_routes.WorkflowExecutorService")
def test_create_workflow(MockExecutor, client):
    mock_instance = MockExecutor.return_value
    mock_instance.create_and_start_workflow.return_value = WorkflowDTO(
        "wf_1", "PENDING", "INPUT", 0, "doc_1", None, None, "now", "now"
    )
    
    settings = get_settings()
    url = f"{settings.api_prefix}/workflow-runs"
    response = client.post(url, json={"document_id": "doc_1"})
    
    assert response.status_code == 200
    assert "workflow_run_id" in response.json()["data"]

@patch("backend.api.routes.workflow_routes.WorkflowService")
def test_get_workflow_observability(MockWorkflowService, client, tmp_path):
    workflow_run_id = "wf_obsv_001"
    mock_workflow = MagicMock()
    mock_workflow.to_dict.return_value = {
        "workflow_run_id": workflow_run_id,
        "status": "RUNNING",
        "current_phase": "GENERATION",
        "overall_progress_percent": 75,
        "document_id": "doc_001",
        "template_id": "tpl_001",
        "phases": [{"phase": "INGESTION", "status": "COMPLETED", "progress_percent": 100}],
        "section_retrieval_results": {
            "sec_1": {"diagnostics": {"cost_summary": {"total_amount": 0.002}}}
        },
        "section_generation_results": {
            "sec_1": {
                "diagnostics": {
                    "cost_metadata": {
                        "estimate": {"amount": 0.0123}
                    }
                }
            },
            "sec_2": {
                "diagnostics": {
                    "cost_metadata": {
                        "estimate": {"amount": 0.0045}
                    }
                }
            },
        },
    }
    MockWorkflowService.return_value.get_workflow.return_value = mock_workflow

    run_root = tmp_path / "ingestion_runs" / workflow_run_id
    logs_dir = run_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    official_log = logs_dir / "official.log"
    official_log.write_text(
        "\n".join(
            [
                json.dumps({"event": "stage_started", "stage_name": "stage_1_runner"}),
                json.dumps({"event": "run_completed", "final_status": "COMPLETED", "safe_metadata": {"cost": {"amount": 0.003}}}),
            ]
        ),
        encoding="utf-8",
    )

    settings = get_settings()
    fake_settings = MagicMock()
    fake_settings.logs_path = tmp_path
    fake_settings.api_prefix = settings.api_prefix
    with patch("backend.api.routes.workflow_routes.get_settings", return_value=fake_settings):
        url = f"{settings.api_prefix}/workflow-runs/{workflow_run_id}/observability"
        response = client.get(url)

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["workflow_run_id"] == workflow_run_id
    assert data["availability"]["official_log_exists"] is True
    assert data["latest_summary"]["latest_ingestion_event"]["event"] == "run_completed"
    assert data["latest_summary"]["ingestion_cost"]["estimated_ingestion_cost_total"] == pytest.approx(0.003)
    assert data["latest_summary"]["retrieval_cost"]["estimated_retrieval_cost_total"] == pytest.approx(0.002)
    assert data["latest_summary"]["generation_cost"]["estimated_generation_cost_total"] == pytest.approx(
        0.0168
    )
    assert data["latest_summary"]["final_observability_summary"]["cost_totals"]["document_total"] == pytest.approx(
        0.0218
    )


# ---------------------------------------------------------------------------
# Output Routes
# ---------------------------------------------------------------------------
@patch("backend.api.routes.output_routes.OutputService")
def test_get_output(MockOutService, client):
    mock_instance = MockOutService.return_value
    mock_instance.get_output.return_value = OutputDTO(
        "out_1", "wf_1", "READY", "DOCUMENT", "DOCX", "now", "now"
    )
    
    settings = get_settings()
    url = f"{settings.api_prefix}/outputs/out_1"
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["data"]["output_id"] == "out_1"


# ---------------------------------------------------------------------------
# Template delete
# ---------------------------------------------------------------------------
@patch("backend.api.routes.template_routes.TemplateAppService")
def test_delete_template(MockTplService, client):
    mock_instance = MockTplService.return_value
    mock_instance.delete_template.return_value = True

    settings = get_settings()
    url = f"{settings.api_prefix}/templates/tpl_del_1"
    response = client.delete(url)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["deleted"] is True
    assert body["data"]["template_id"] == "tpl_del_1"
    mock_instance.delete_template.assert_called_once_with("tpl_del_1")
