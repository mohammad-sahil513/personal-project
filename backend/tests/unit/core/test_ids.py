"""
Tests for ID generation utilities.
"""

from __future__ import annotations

from backend.core import ids


def test_generate_document_id():
    doc_id = ids.generate_document_id()
    assert doc_id.startswith("doc_")
    assert len(doc_id) == 4 + 12  # 'doc_' + 12 hex chars


def test_generate_template_id():
    tpl_id = ids.generate_template_id()
    assert tpl_id.startswith("tpl_")


def test_generate_workflow_run_id():
    wf_id = ids.generate_workflow_run_id()
    assert wf_id.startswith("wf_")


def test_generate_job_id():
    job_id = ids.generate_job_id()
    assert job_id.startswith("job_")
    custom_job_id = ids.generate_job_id("prefix")
    assert custom_job_id.startswith("prefix_")


def test_generate_output_id():
    out_id = ids.generate_output_id()
    assert out_id.startswith("out_")


def test_generate_execution_id():
    exec_id = ids.generate_execution_id()
    assert exec_id.startswith("exec_")
