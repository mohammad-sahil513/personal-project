"""
Section executor for the Generation module.

Responsibilities:
- Execute one section end-to-end
- Guard on dependency readiness
- Call Retrieval exactly once per section
- Assemble the prompt
- Route to the correct generation strategy
- Validate output
- Use bounded correction on validation failure (text/table only)
- Apply low-evidence degradation rules
- Emit SSE events
- Invoke an optional snapshot hook
- Emit shared observability logs and cost estimates

Important:
- This file is section-level orchestration only.
- It does NOT perform document-level wave planning or final assembly/export.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.generation.contracts.generation_contracts import (
    GenerationStrategy,
    GenerationWarningCode,
    OutputType,
    SectionExecutionStatus,
    SectionGenerationResult,
    SectionOutput,
)
from backend.modules.generation.generators.diagram_generator import (
    DiagramGenerationRequest,
    DiagramGenerationResponse,
    DiagramGenerator,
)
from backend.modules.generation.generators.prompt_assembler import (
    ConflictEvidenceItem,
    EvidenceTextItem,
    PromptAssembler,
    PromptAssemblyRequest,
    PromptAssemblyResult,
    RollingContextItem,
    TableEvidenceItem,
)
from backend.modules.generation.generators.table_generator import (
    TableGenerationRequest,
    TableGenerationResponse,
    TableGenerator,
)
from backend.modules.generation.generators.text_generator import (
    TextGenerationRequest,
    TextGenerationResponse,
    TextGenerator,
)
from backend.modules.generation.models.generation_config import (
    DEFAULT_GENERATION_CONFIG,
    GenerationConfig,
)
from backend.modules.generation.streaming.sse_publisher import (
    SSEEventType,
    SSEPublisher,
)
from backend.modules.generation.validators.correction_loop import (
    CorrectionLoop,
    CorrectionLoopRequest,
)
from backend.modules.generation.validators.output_validator import (
    OutputValidationRequest,
    OutputValidationResult,
    OutputValidationRules,
    OutputValidator,
)
from backend.modules.observability.services.cost_aggregation_service import (
    CostAggregationService,
)
from backend.modules.observability.services.cost_estimator_service import (
    CostEstimatorService,
)
from backend.modules.observability.services.logging_service import (
    LoggingService,
)
from backend.modules.observability.services.request_context_service import (
    RequestContextService,
)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------------------
# Retrieval / snapshot protocols
# ------------------------------------------------------------------------------


class RetrievalExecutionResult(BaseModel):
    """
    Generation-facing Retrieval result for one target section.

    This preserves the Retrieval boundary:
    one retrieval call -> one target section -> one evidence bundle.
    """

    model_config = ConfigDict(extra="forbid")

    retrieval_id: str | None = Field(default=None)
    retrieval_status: str = Field(
        description="Retrieval status string (e.g. OK/PARTIAL/INSUFFICIENT_EVIDENCE/FAILED)."
    )
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    source_evidence: list[EvidenceTextItem] = Field(default_factory=list)
    guideline_evidence: list[EvidenceTextItem] = Field(default_factory=list)
    exemplar_evidence: list[EvidenceTextItem] = Field(default_factory=list)
    table_evidence: list[TableEvidenceItem] = Field(default_factory=list)
    conflict_evidence: list[ConflictEvidenceItem] = Field(default_factory=list)


@runtime_checkable
class RetrievalExecutor(Protocol):
    """
    Protocol for the section-scoped Retrieval dependency.
    """

    def retrieve(
        self,
        *,
        section_id: str,
        section_heading: str,
        strategy: GenerationStrategy,
        retrieval_context: dict[str, Any] | None = None,
    ) -> RetrievalExecutionResult:
        """
        Retrieve evidence for one target section.
        """
        ...


@runtime_checkable
class SectionSnapshotWriter(Protocol):
    """
    Optional snapshot hook invoked after section completion/failure.
    """

    def snapshot_section_result(
        self,
        *,
        job_id: str,
        result: SectionGenerationResult,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Persist a section snapshot and return snapshot metadata.
        """
        ...


# ------------------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------------------


class SectionExecutionRequest(BaseModel):
    """
    Input payload for executing one Generation section.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(description="Stable Generation job identifier.")
    document_id: str | None = Field(default=None, description="Document identifier for observability correlation.")
    template_id: str | None = Field(default=None, description="Template identifier for observability correlation.")
    template_version: str | None = Field(default=None, description="Template version for observability correlation.")

    section_id: str = Field(description="Stable section identifier.")
    section_heading: str = Field(description="Section heading/title.")
    strategy: GenerationStrategy = Field(description="Resolved Generation strategy.")
    prompt_key: str = Field(description="Resolved prompt key.")
    validation_rules: OutputValidationRules = Field(
        default_factory=OutputValidationRules,
        description="Section-level validation rules.",
    )
    section_intent: str | None = Field(default=None)
    extra_instructions: str | None = Field(default=None)
    retrieval_context: dict[str, Any] = Field(default_factory=dict)
    rolling_context: list[RollingContextItem] = Field(default_factory=list)
    dependencies_satisfied: bool = Field(
        default=True,
        description="Guard value produced by dependency-aware orchestration.",
    )
    model_name: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SectionExecutionResponse(BaseModel):
    """
    Final section-execution response.
    """

    model_config = ConfigDict(extra="forbid")

    result: SectionGenerationResult = Field(description="Final structured section result.")
    prompt_assembly: PromptAssemblyResult | None = Field(
        default=None,
        description="Prompt assembly diagnostics/result used for the section.",
    )
    retrieval: RetrievalExecutionResult | None = Field(
        default=None,
        description="Retrieval result used during section execution.",
    )
    validation_result: OutputValidationResult | None = Field(
        default=None,
        description="Final validation result for the chosen output.",
    )
    snapshot_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional snapshot metadata from the snapshot hook.",
    )
    cost_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional cost estimation / aggregation metadata for observability.",
    )


# ------------------------------------------------------------------------------
# Section Executor
# ------------------------------------------------------------------------------


class SectionExecutor:
    """
    Executes one section end-to-end.

    Flow:
    - dependency guard
    - Retrieval
    - prompt assembly
    - strategy dispatch
    - low-evidence handling
    - validation
    - correction (text/table only)
    - final result construction
    - SSE + snapshot hook
    - shared observability logging + cost estimation
    """

    def __init__(
        self,
        *,
        retrieval_executor: RetrievalExecutor,
        prompt_assembler: PromptAssembler,
        text_generator: TextGenerator,
        table_generator: TableGenerator,
        diagram_generator: DiagramGenerator,
        output_validator: OutputValidator,
        correction_loop: CorrectionLoop,
        sse_publisher: SSEPublisher,
        logging_service: LoggingService | None = None,
        request_context_service: RequestContextService | None = None,
        cost_estimator_service: CostEstimatorService | None = None,
        cost_aggregation_service: CostAggregationService | None = None,
        snapshot_writer: SectionSnapshotWriter | None = None,
        config: GenerationConfig | None = None,
    ) -> None:
        if not isinstance(retrieval_executor, RetrievalExecutor):
            raise TypeError("retrieval_executor must implement RetrievalExecutor.")

        self.retrieval_executor = retrieval_executor
        self.prompt_assembler = prompt_assembler
        self.text_generator = text_generator
        self.table_generator = table_generator
        self.diagram_generator = diagram_generator
        self.output_validator = output_validator
        self.correction_loop = correction_loop
        self.sse_publisher = sse_publisher

        self.request_context_service = request_context_service or RequestContextService()
        self.logging_service = logging_service or LoggingService(
            context_provider=self.request_context_service.get_context_dict
        )
        self.cost_estimator_service = cost_estimator_service
        self.cost_aggregation_service = cost_aggregation_service

        self.snapshot_writer = snapshot_writer
        self.config = config or DEFAULT_GENERATION_CONFIG

    def execute(self, request: SectionExecutionRequest) -> SectionExecutionResponse:
        """
        Execute one Generation section.
        """
        started_at = utc_now()
        cost_metadata: dict[str, Any] | None = None

        # Set shared correlation context for observability
        self.request_context_service.start_job_context(
            job_id=request.job_id,
            document_id=request.document_id,
            template_id=request.template_id,
            template_version=request.template_version,
            section_id=request.section_id,
        )

        self.logging_service.info(
            "generation_section_started",
            job_id=request.job_id,
            document_id=request.document_id,
            template_id=request.template_id,
            template_version=request.template_version,
            section_id=request.section_id,
            strategy=request.strategy.value,
        )

        # ------------------------------------------------------------------
        # Dependency guard
        # ------------------------------------------------------------------
        if not request.dependencies_satisfied:
            result = SectionGenerationResult(
                section_id=request.section_id,
                section_heading=request.section_heading,
                strategy=request.strategy,
                status=SectionExecutionStatus.SKIPPED,
                warnings=[],
                manual_review_required=False,
                error_message=None,
                started_at=started_at,
                completed_at=utc_now(),
            )

            self.logging_service.warning(
                "generation_section_dependency_not_satisfied",
                section_id=request.section_id,
                strategy=request.strategy.value,
            )

            self.sse_publisher.publish(
                job_id=request.job_id,
                event=SSEEventType.SECTION_FAILED,
                section_id=request.section_id,
                outcome="dependency_not_satisfied",
                data={"strategy": request.strategy.value},
            )

            snapshot_metadata = self._snapshot_if_configured(
                job_id=request.job_id,
                result=result,
                metadata={"reason": "dependency_not_satisfied"},
            )

            self.request_context_service.clear_context()

            return SectionExecutionResponse(
                result=result,
                prompt_assembly=None,
                retrieval=None,
                validation_result=None,
                snapshot_metadata=snapshot_metadata,
                cost_metadata=None,
            )

        # ------------------------------------------------------------------
        # Start event
        # ------------------------------------------------------------------
        self.sse_publisher.publish(
            job_id=request.job_id,
            event=SSEEventType.SECTION_STARTED,
            section_id=request.section_id,
            outcome="running",
            data={"strategy": request.strategy.value},
        )

        # ------------------------------------------------------------------
        # Retrieval (exactly one call per section)
        # ------------------------------------------------------------------
        retrieval_result = self.retrieval_executor.retrieve(
            section_id=request.section_id,
            section_heading=request.section_heading,
            strategy=request.strategy,
            retrieval_context=request.retrieval_context,
        )

        self.logging_service.info(
            "generation_retrieval_completed",
            section_id=request.section_id,
            retrieval_id=retrieval_result.retrieval_id,
            retrieval_status=retrieval_result.retrieval_status,
            source_evidence_count=len(retrieval_result.source_evidence),
            guideline_evidence_count=len(retrieval_result.guideline_evidence),
            exemplar_evidence_count=len(retrieval_result.exemplar_evidence),
            table_evidence_count=len(retrieval_result.table_evidence),
            conflict_evidence_count=len(retrieval_result.conflict_evidence),
        )

        if retrieval_result.retrieval_status.upper() == "FAILED":
            failed_result = SectionGenerationResult(
                section_id=request.section_id,
                section_heading=request.section_heading,
                strategy=request.strategy,
                status=SectionExecutionStatus.FAILED,
                warnings=[],
                manual_review_required=False,
                error_message="Retrieval failed for section execution.",
                started_at=started_at,
                completed_at=utc_now(),
            )

            self.logging_service.error(
                "generation_section_failed",
                section_id=request.section_id,
                strategy=request.strategy.value,
                reason="retrieval_failed",
                retrieval_id=retrieval_result.retrieval_id,
            )

            self.sse_publisher.publish(
                job_id=request.job_id,
                event=SSEEventType.SECTION_FAILED,
                section_id=request.section_id,
                outcome="retrieval_failed",
                data={"retrieval_id": retrieval_result.retrieval_id},
            )

            snapshot_metadata = self._snapshot_if_configured(
                job_id=request.job_id,
                result=failed_result,
                metadata={"retrieval_id": retrieval_result.retrieval_id},
            )

            self.request_context_service.clear_context()

            return SectionExecutionResponse(
                result=failed_result,
                prompt_assembly=None,
                retrieval=retrieval_result,
                validation_result=None,
                snapshot_metadata=snapshot_metadata,
                cost_metadata=None,
            )

        # ------------------------------------------------------------------
        # Prompt assembly
        # ------------------------------------------------------------------
        prompt_result = self.prompt_assembler.assemble(
            PromptAssemblyRequest(
                section_id=request.section_id,
                section_heading=request.section_heading,
                strategy=request.strategy,
                prompt_key=request.prompt_key,
                section_intent=request.section_intent,
                extra_instructions=request.extra_instructions,
                source_evidence=retrieval_result.source_evidence,
                guideline_evidence=retrieval_result.guideline_evidence,
                exemplar_evidence=retrieval_result.exemplar_evidence,
                table_evidence=retrieval_result.table_evidence,
                conflict_evidence=retrieval_result.conflict_evidence,
                rolling_context=request.rolling_context,
            )
        )

        self.logging_service.info(
            "generation_prompt_assembled",
            section_id=request.section_id,
            strategy=request.strategy.value,
            prompt_key_used=prompt_result.prompt_key_used,
            estimated_tokens=prompt_result.estimated_tokens,
            included_source_facts=prompt_result.included_source_facts,
            included_guidelines=prompt_result.included_guidelines,
            included_exemplars=prompt_result.included_exemplars,
            included_tables=prompt_result.included_tables,
            included_conflicts=prompt_result.included_conflicts,
            included_rolling_context_sections=prompt_result.included_rolling_context_sections,
        )

        # ------------------------------------------------------------------
        # Strategy dispatch
        # ------------------------------------------------------------------
        output, generator_metadata, diagram_repair_used = self._generate_output(
            request=request,
            prompt_result=prompt_result,
        )

        self.logging_service.info(
            "generation_strategy_executed",
            section_id=request.section_id,
            strategy=request.strategy.value,
            output_type=output.output_type.value,
            diagram_repair_used=diagram_repair_used,
        )

        # ------------------------------------------------------------------
        # Low-evidence rule
        # ------------------------------------------------------------------
        low_evidence = len(retrieval_result.source_evidence) < self.config.low_evidence_min_source_facts
        warnings: list[GenerationWarningCode] = []
        manual_review_required = False

        if low_evidence and output.output_type in {OutputType.MARKDOWN_TEXT, OutputType.MARKDOWN_TABLE}:
            output = self._apply_low_evidence_prefix(output)
            warnings.append(GenerationWarningCode.LOW_EVIDENCE)
            warnings.append(GenerationWarningCode.STRATEGY_DEGRADED)
            manual_review_required = True

            self.logging_service.warning(
                "generation_low_evidence_detected",
                section_id=request.section_id,
                strategy=request.strategy.value,
                source_evidence_count=len(retrieval_result.source_evidence),
                threshold=self.config.low_evidence_min_source_facts,
            )

        if diagram_repair_used:
            warnings.append(GenerationWarningCode.DIAGRAM_REPAIR_USED)

        # ------------------------------------------------------------------
        # Validation
        # ------------------------------------------------------------------
        effective_rules = request.validation_rules.model_copy(
            update={"require_low_evidence_prefix": low_evidence}
        )
        validation_result = self.output_validator.validate(
            OutputValidationRequest(
                section_id=request.section_id,
                section_heading=request.section_heading,
                strategy=request.strategy,
                output=output,
                rules=effective_rules,
                low_evidence=low_evidence,
            )
        )

        self.logging_service.info(
            "generation_validation_completed",
            section_id=request.section_id,
            strategy=request.strategy.value,
            is_valid=validation_result.is_valid,
            issue_count=len(validation_result.issues),
        )

        correction_used = False

        # Text/table only correction on validation failure
        if not validation_result.is_valid and request.strategy != GenerationStrategy.DIAGRAM_PLANTUML:
            correction_result = self.correction_loop.retry(
                CorrectionLoopRequest(
                    section_id=request.section_id,
                    section_heading=request.section_heading,
                    strategy=request.strategy,
                    original_prompt_text=prompt_result.prompt_text,
                    initial_output=output,
                    initial_validation_result=validation_result,
                    validation_rules=effective_rules,
                    low_evidence=low_evidence,
                    model_name=request.model_name,
                    metadata=request.metadata,
                    max_retries=self.config.max_retries,
                )
            )

            output = correction_result.final_output
            validation_result = correction_result.final_validation_result

            if correction_result.attempts_used > 0:
                correction_used = True
                warnings.append(GenerationWarningCode.VALIDATION_RETRY_USED)

                self.logging_service.info(
                    "generation_correction_retry_used",
                    section_id=request.section_id,
                    strategy=request.strategy.value,
                    attempts_used=correction_result.attempts_used,
                    final_valid=correction_result.final_validation_result.is_valid,
                )

        # ------------------------------------------------------------------
        # Cost estimation / aggregation (best-effort, non-blocking)
        # ------------------------------------------------------------------
        cost_metadata = self._estimate_and_aggregate_cost(
            request=request,
            prompt_result=prompt_result,
            output=output,
            generator_metadata=generator_metadata,
        )

        # ------------------------------------------------------------------
        # Final result construction
        # ------------------------------------------------------------------
        if validation_result.is_valid:
            final_status = (
                SectionExecutionStatus.DEGRADED
                if low_evidence
                else SectionExecutionStatus.GENERATED
            )
            result = SectionGenerationResult(
                section_id=request.section_id,
                section_heading=request.section_heading,
                strategy=request.strategy,
                status=final_status,
                output=output,
                warnings=warnings,
                low_evidence=low_evidence,
                manual_review_required=manual_review_required,
                error_message=None,
                started_at=started_at,
                completed_at=utc_now(),
            )

            self.logging_service.info(
                "generation_section_completed",
                section_id=request.section_id,
                strategy=request.strategy.value,
                status=final_status.value,
                validation_retry_used=correction_used,
                low_evidence=low_evidence,
            )

            self.sse_publisher.publish(
                job_id=request.job_id,
                event=SSEEventType.SECTION_COMPLETED,
                section_id=request.section_id,
                outcome=final_status.value,
                data={
                    "strategy": request.strategy.value,
                    "retrieval_id": retrieval_result.retrieval_id,
                    "validation_retry_used": correction_used,
                    "diagram_repair_used": diagram_repair_used,
                },
            )
        else:
            result = SectionGenerationResult(
                section_id=request.section_id,
                section_heading=request.section_heading,
                strategy=request.strategy,
                status=SectionExecutionStatus.FAILED,
                warnings=warnings,
                low_evidence=low_evidence,
                manual_review_required=manual_review_required,
                error_message="Section output failed validation after retries.",
                started_at=started_at,
                completed_at=utc_now(),
            )

            self.logging_service.error(
                "generation_section_failed",
                section_id=request.section_id,
                strategy=request.strategy.value,
                reason="validation_failed",
                issue_count=len(validation_result.issues),
            )

            self.sse_publisher.publish(
                job_id=request.job_id,
                event=SSEEventType.SECTION_FAILED,
                section_id=request.section_id,
                outcome="validation_failed",
                data={
                    "strategy": request.strategy.value,
                    "retrieval_id": retrieval_result.retrieval_id,
                    "issue_count": len(validation_result.issues),
                },
            )

        snapshot_metadata = self._snapshot_if_configured(
            job_id=request.job_id,
            result=result,
            metadata={
                "retrieval_id": retrieval_result.retrieval_id,
                "strategy": request.strategy.value,
            },
        )

        self.request_context_service.clear_context()

        return SectionExecutionResponse(
            result=result,
            prompt_assembly=prompt_result,
            retrieval=retrieval_result,
            validation_result=validation_result,
            snapshot_metadata=snapshot_metadata,
            cost_metadata=cost_metadata,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_output(
        self,
        *,
        request: SectionExecutionRequest,
        prompt_result: PromptAssemblyResult,
    ) -> tuple[SectionOutput, dict[str, Any], bool]:
        """
        Route to the correct strategy generator.
        """
        if request.strategy == GenerationStrategy.SUMMARIZE_TEXT:
            response: TextGenerationResponse = self.text_generator.generate(
                TextGenerationRequest(
                    section_id=request.section_id,
                    section_heading=request.section_heading,
                    prompt_text=prompt_result.prompt_text,
                    prompt_key_used=prompt_result.prompt_key_used,
                    model_name=request.model_name,
                    metadata=request.metadata,
                )
            )
            return response.output, response.backend_metadata, False

        if request.strategy == GenerationStrategy.GENERATE_TABLE:
            response: TableGenerationResponse = self.table_generator.generate(
                TableGenerationRequest(
                    section_id=request.section_id,
                    section_heading=request.section_heading,
                    prompt_text=prompt_result.prompt_text,
                    prompt_key_used=prompt_result.prompt_key_used,
                    model_name=request.model_name,
                    metadata=request.metadata,
                )
            )
            return response.output, response.backend_metadata, False

        response: DiagramGenerationResponse = self.diagram_generator.generate(
            DiagramGenerationRequest(
                section_id=request.section_id,
                section_heading=request.section_heading,
                prompt_text=prompt_result.prompt_text,
                prompt_key_used=prompt_result.prompt_key_used,
                model_name=request.model_name,
                metadata=request.metadata,
            )
        )
        return response.output, response.backend_metadata, response.render_repair_used

    def _apply_low_evidence_prefix(self, output: SectionOutput) -> SectionOutput:
        """
        Apply the locked [LOW EVIDENCE] prefix to markdown outputs.
        """
        if output.output_type not in {OutputType.MARKDOWN_TEXT, OutputType.MARKDOWN_TABLE}:
            return output

        content = output.content_markdown or ""
        stripped = content.lstrip()
        if stripped.startswith("[LOW EVIDENCE]"):
            return output

        prefixed = "[LOW EVIDENCE]\n\n" + content.strip()
        return SectionOutput(
            output_type=output.output_type,
            content_markdown=prefixed,
            diagram_artifacts=None,
            metadata=output.metadata,
        )

    def _snapshot_if_configured(
        self,
        *,
        job_id: str,
        result: SectionGenerationResult,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Invoke the snapshot writer only when configured.
        """
        if not self.config.snapshot_after_each_section:
            return None

        if self.snapshot_writer is None:
            return None

        return self.snapshot_writer.snapshot_section_result(
            job_id=job_id,
            result=result,
            metadata=metadata or {},
        )

    def _estimate_and_aggregate_cost(
        self,
        *,
        request: SectionExecutionRequest,
        prompt_result: PromptAssemblyResult,
        output: SectionOutput,
        generator_metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Best-effort section cost estimation + aggregation.

        This must never fail the actual Generation flow.
        """
        if self.cost_estimator_service is None:
            return None

        model_name = (
            str(generator_metadata.get("model"))
            if generator_metadata.get("model") is not None
            else request.model_name
        )

        if not model_name:
            return None

        prompt_tokens = int(prompt_result.estimated_tokens)
        usage_tokens = self._extract_usage_tokens(generator_metadata)
        if usage_tokens.get("prompt_tokens") is not None:
            prompt_tokens = int(usage_tokens["prompt_tokens"])
        completion_tokens = self._estimate_completion_tokens(output, generator_metadata)

        try:
            if request.strategy == GenerationStrategy.DIAGRAM_PLANTUML:
                estimate = self.cost_estimator_service.estimate_diagram_section_cost(
                    model_name=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    section_id=request.section_id,
                )
                category = "diagram_section"
            else:
                estimate = self.cost_estimator_service.estimate_generation_section_cost(
                    model_name=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    section_id=request.section_id,
                    strategy=request.strategy.value,
                )
                category = "generation_section"

            aggregated = None
            if self.cost_aggregation_service is not None:
                record = self.cost_aggregation_service.add_cost_record(
                    job_id=request.job_id,
                    category=category,
                    estimate=estimate,
                    section_id=request.section_id,
                    metadata={
                        "strategy": request.strategy.value,
                    },
                )
                aggregated = {
                    "record_category": record.category,
                    "record_amount": record.estimate.amount,
                }
                summary = self.cost_aggregation_service.get_summary(request.job_id)
                aggregated["document_total_amount"] = summary.total_amount
                aggregated["section_total_amount"] = summary.by_section.get(request.section_id, 0.0)

            self.logging_service.info(
                "generation_llm_usage_and_cost",
                section_id=request.section_id,
                strategy=request.strategy.value,
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=usage_tokens.get("total_tokens", prompt_tokens + completion_tokens),
                estimated_amount=estimate.amount,
                currency=estimate.currency,
                document_id=request.document_id,
                job_id=request.job_id,
                stage="generation_section",
                section_cost_total=(aggregated or {}).get("section_total_amount"),
                document_cost_total=(aggregated or {}).get("document_total_amount"),
            )

            return {
                "estimate": estimate.model_dump(),
                "aggregation": aggregated,
            }
        except Exception as exc:
            # Cost estimation should not break Generation execution.
            self.logging_service.warning(
                "generation_cost_estimation_failed",
                section_id=request.section_id,
                strategy=request.strategy.value,
                model_name=model_name,
                error_message=str(exc),
            )
            return {
                "error": str(exc),
            }

    def _estimate_completion_tokens(
        self,
        output: SectionOutput,
        generator_metadata: dict[str, Any],
    ) -> int:
        """
        Estimate completion tokens using backend metadata when available,
        otherwise fall back to a simple text-length heuristic.
        """
        usage_tokens = self._extract_usage_tokens(generator_metadata)
        explicit = usage_tokens.get("completion_tokens")
        if explicit is None:
            explicit = generator_metadata.get("completion_tokens")
        if isinstance(explicit, int) and explicit >= 0:
            return explicit

        text = ""
        if output.output_type in {OutputType.MARKDOWN_TEXT, OutputType.MARKDOWN_TABLE}:
            text = output.content_markdown or ""
        elif output.output_type == OutputType.DIAGRAM_ARTIFACT:
            text = generator_metadata.get("normalized_puml_text", "") or ""

        if not text:
            return 0

        # Same simple heuristic used elsewhere: ~1 token ~= 4 chars
        return max(1, len(text) // 4)

    def _extract_usage_tokens(self, generator_metadata: dict[str, Any]) -> dict[str, int]:
        usage: dict[str, Any] = {}
        direct_usage = generator_metadata.get("usage")
        if isinstance(direct_usage, dict):
            usage.update(direct_usage)

        source_backend = generator_metadata.get("source_backend")
        if isinstance(source_backend, dict):
            nested_usage = source_backend.get("usage")
            if isinstance(nested_usage, dict):
                usage.update(nested_usage)

        normalized: dict[str, int] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                normalized[key] = value
        return normalized
