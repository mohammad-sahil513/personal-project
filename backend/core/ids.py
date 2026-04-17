"""
ID generation helpers for backend entities.
"""

from uuid import uuid4


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def generate_document_id() -> str:
    return _generate_id("doc")


def generate_template_id() -> str:
    return _generate_id("tpl")


def generate_workflow_run_id() -> str:
    return _generate_id("wf")


def generate_job_id(prefix: str = "job") -> str:
    return _generate_id(prefix)


def generate_output_id() -> str:
    return _generate_id("out")


def generate_execution_id() -> str:
    return _generate_id("exec")