# 13 - API Examples

This document provides practical request/response examples for the main backend APIs.

Base URL examples assume:
- `http://localhost:8000`
- API prefix from config defaults to `/api/v1`

So endpoint root is:
- `http://localhost:8000/api/v1`

---

## 1) Health Checks

## Request
```bash
curl -X GET "http://localhost:8000/api/v1/health"
```

## Response (example)
```json
{
  "success": true,
  "message": "Service is healthy",
  "data": {
    "status": "ok"
  }
}
```

---

## 2) Upload a Document

## Request
```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -F "file=@sample_input.docx"
```

## Response (example)
```json
{
  "success": true,
  "message": "Document uploaded successfully",
  "data": {
    "document_id": "doc_123abc",
    "filename": "sample_input.docx",
    "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "size": 24567,
    "uploaded_at": "2026-04-16T10:15:30.123456+00:00",
    "status": "AVAILABLE"
  }
}
```

---

## 3) Upload a Template

## Request
```bash
curl -X POST "http://localhost:8000/api/v1/templates/upload" \
  -F "file=@template.docx" \
  -F "template_type=SDLC" \
  -F "version=v1"
```

## Response (example)
```json
{
  "success": true,
  "message": "Template uploaded successfully",
  "data": {
    "template_id": "tpl_456def",
    "filename": "template.docx",
    "template_type": "SDLC",
    "version": "v1",
    "status": "UPLOADED"
  }
}
```

---

## 4) Start Template Compile

## Request
```bash
curl -X POST "http://localhost:8000/api/v1/templates/tpl_456def/compile" \
  -H "Content-Type: application/json" \
  -d "{}"
```

## Response (example)
```json
{
  "success": true,
  "message": "Template compilation started",
  "data": {
    "template_id": "tpl_456def",
    "status": "COMPILING",
    "compile_job_id": "cmp_001",
    "dispatch_mode": "BACKGROUND_TASK"
  }
}
```

---

## 5) Create Workflow Run

## Request
```bash
curl -X POST "http://localhost:8000/api/v1/workflow-runs" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "doc_123abc",
    "template_id": "tpl_456def",
    "start_immediately": true
  }'
```

## Response (example)
```json
{
  "success": true,
  "message": "Workflow created successfully",
  "data": {
    "workflow_run_id": "wf_789ghi",
    "status": "RUNNING",
    "current_phase": "INPUT_PREPARATION",
    "overall_progress_percent": 0,
    "dispatch_mode": "BACKGROUND_TASK"
  }
}
```

---

## 6) Get Workflow Status

## Request
```bash
curl -X GET "http://localhost:8000/api/v1/workflow-runs/wf_789ghi/status"
```

## Response (example)
```json
{
  "success": true,
  "message": "Workflow status fetched successfully",
  "data": {
    "workflow_run_id": "wf_789ghi",
    "status": "RUNNING",
    "current_phase": "INGESTION",
    "overall_progress_percent": 32,
    "current_step_label": "Stage 03 - Masking PII",
    "ingestion": {
      "status": "RUNNING",
      "current_stage": "03_MASK_PII",
      "completed_stages": 2,
      "total_stages": 9
    }
  }
}
```

---

## 7) Stream Workflow Events (SSE)

## Request
```bash
curl -N "http://localhost:8000/api/v1/workflow-runs/wf_789ghi/events"
```

## Event stream payload (example)
```text
event: workflow.update
data: {"event_type":"section.retrieval.started","phase":"retrieval","payload":{"section_id":"sec_1"}}
```

---

## 8) Get Workflow Observability

## Request
```bash
curl -X GET "http://localhost:8000/api/v1/workflow-runs/wf_789ghi/observability"
```

## Response (example)
```json
{
  "success": true,
  "message": "Workflow observability fetched successfully",
  "data": {
    "workflow_run_id": "wf_789ghi",
    "latest_summary": {
      "workflow_status": "RUNNING",
      "current_phase": "GENERATION",
      "ingestion_cost": {"estimated_ingestion_cost_total": 0.12},
      "retrieval_cost": {"estimated_retrieval_cost_total": 0.07},
      "generation_cost": {"estimated_generation_cost_total": 0.21}
    }
  }
}
```

---

## 9) Get Output Metadata

## Request
```bash
curl -X GET "http://localhost:8000/api/v1/outputs/out_123xyz"
```

## Response (example)
```json
{
  "success": true,
  "message": "Output fetched successfully",
  "data": {
    "output_id": "out_123xyz",
    "workflow_run_id": "wf_789ghi",
    "status": "READY",
    "format": "DOCX",
    "artifact_path": "storage/outputs/wf_789ghi/out_123xyz.docx"
  }
}
```

---

## 10) Download Output

## Request
```bash
curl -L "http://localhost:8000/api/v1/outputs/out_123xyz/download" -o final.docx
```

---

## Notes

- Exact response fields can evolve as DTOs and services evolve.
- All successful endpoints follow a standardized response envelope.
- Use workflow status + events + observability endpoints together for best runtime visibility.
