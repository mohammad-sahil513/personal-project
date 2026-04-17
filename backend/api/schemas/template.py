"""
API schema models for template routes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TemplateArtifactDescriptor(BaseModel):
    name: str
    artifact_type: str
    file_path: str | None = None


class TemplateCreateRequest(BaseModel):
    filename: str
    template_type: str | None = None
    version: str | None = None


class TemplateCompileRequest(BaseModel):
    use_ai_assist: bool = True
    publish_artifacts: bool = False


class TemplateSummaryResponseData(BaseModel):
    template_id: str
    filename: str
    template_type: str | None = None
    version: str | None = None
    status: str
    created_at: str
    updated_at: str
    compile_job_id: str | None = None
    compiled_artifacts: list[TemplateArtifactDescriptor] = Field(default_factory=list)


class TemplateListResponseData(BaseModel):
    items: list[TemplateSummaryResponseData]
    total: int


class TemplateCompileResponseData(TemplateSummaryResponseData):
    dispatch_mode: str | None = None


class CompiledTemplateResponseData(BaseModel):
    template_id: str
    filename: str
    status: str
    compiled_artifacts: list[TemplateArtifactDescriptor] = Field(default_factory=list)


class TemplateValidationResponseData(BaseModel):
    template_id: str
    is_valid: bool
    errors: list[dict] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)


class ResolvedTemplateSection(BaseModel):
    section_id: str | None = None
    title: str | None = None
    execution_order: int | None = None
    generation_strategy: str | None = None


class TemplateResolveResponseData(BaseModel):
    template_id: str
    resolved_sections: list[dict] = Field(default_factory=list)