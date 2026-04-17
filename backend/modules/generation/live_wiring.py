from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from backend.core.exceptions import ConfigurationError, ValidationError
from backend.core.ids import generate_workflow_run_id
from backend.modules.observability.services.cost_aggregation_service import (
    CostAggregationService,
)
from backend.modules.observability.services.cost_estimator_service import (
    CostEstimatorService,
)
from backend.modules.observability.services.logging_service import LoggingService
from backend.modules.observability.services.pricing_registry_service import (
    PricingRegistryService,
)
from backend.modules.observability.services.request_context_service import (
    RequestContextService,
)


def _default_map_output_type(generation_strategy: str) -> str:
    normalized = (generation_strategy or "").strip().lower()
    if normalized == "generate_table":
        return "markdown_table"
    if normalized == "diagram_plantuml":
        return "diagram_artifact"
    return "markdown_text"


def build_generation_runtime_callable(
    *,
    output_type_mapper: Callable[[str], str] | None = None,
) -> Callable[..., Any]:
    """
    Build generation runtime callable with live module wiring.
    """
    try:
        from backend.modules.generation.contracts.generation_contracts import (
            GenerationStrategy,
            SectionExecutionStatus,
        )
        from backend.modules.generation.diagram.diagram_artifact_store import (
            DiagramArtifactStoreService,
        )
        from backend.modules.generation.diagram.diagram_embedder import (
            DiagramEmbedderService,
        )
        from backend.modules.generation.diagram.kroki_client import (
            KrokiClientService,
            KrokiOutputFormat,
        )
        from backend.modules.generation.diagram.plantuml_normalizer import (
            PlantUMLNormalizerService,
        )
        from backend.modules.generation.diagram.plantuml_validator import (
            PlantUMLValidatorService,
        )
        from backend.modules.generation.diagram.repair_loop import (
            DiagramRepairLoopService,
        )
        from backend.modules.generation.generators.diagram_generator import (
            DiagramGenerator,
        )
        from backend.modules.generation.generators.prompt_assembler import (
            ConflictEvidenceItem,
            EvidenceTextItem,
            PromptAssembler,
            TableEvidenceItem,
        )
        from backend.modules.generation.generators.table_generator import (
            TableGenerator,
        )
        from backend.modules.generation.generators.text_generator import TextGenerator
        from backend.modules.generation.models.generation_config import (
            DEFAULT_GENERATION_CONFIG,
        )
        from backend.modules.generation.orchestrators.section_executor import (
            RetrievalExecutionResult,
            SectionExecutionRequest,
            SectionExecutor,
        )
        from backend.modules.generation.streaming.sse_publisher import SSEPublisher
        from backend.modules.generation.validators.correction_loop import (
            CorrectionLoop,
        )
        from backend.modules.generation.validators.output_validator import (
            OutputValidator,
        )
        from backend.core.config import get_settings
        from backend.infrastructure.ai_clients.sk_unified_adapter import (
            AzureSemanticKernelTextAdapter,
        )
    except Exception as exc:
        raise ConfigurationError(
            message=(
                "Failed to import generation runtime dependencies. "
                "Ensure generation module dependencies are installed."
            ),
            error_code="GENERATION_RUNTIME_IMPORT_FAILED",
            details={"reason": str(exc)},
        ) from exc

    settings = get_settings()
    endpoint = (settings.azure_openai_endpoint or "").strip()
    api_key = (settings.azure_openai_api_key or "").strip()
    deployment = (
        (settings.azure_openai_chat_deployment or "").strip()
        or (settings.azure_openai_reasoning_deployment or "").strip()
    )

    missing: list[str] = []
    if not endpoint:
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not api_key:
        missing.append("AZURE_OPENAI_API_KEY")
    if not deployment:
        missing.append(
            "AZURE_OPENAI_CHAT_DEPLOYMENT (or AZURE_OPENAI_REASONING_DEPLOYMENT)"
        )
    if missing:
        raise ConfigurationError(
            message="Generation runtime is not configured for Azure OpenAI.",
            error_code="GENERATION_RUNTIME_NOT_CONFIGURED",
            details={"missing": missing},
        )

    sk_text_adapter = AzureSemanticKernelTextAdapter(
        settings=settings,
        endpoint=endpoint,
        api_key=api_key,
        api_version=settings.azure_openai_api_version,
        deployments=[
            {"alias": "gpt5mini", "deployment_name": (settings.azure_openai_chat_deployment or "").strip() or deployment},
            {"alias": "gpt5", "deployment_name": (settings.azure_openai_reasoning_deployment or "").strip() or deployment},
        ],
        default_deployment_alias="gpt5mini",
    )
    map_output_type = output_type_mapper or _default_map_output_type

    class _LLMBackend:
        def _call(
            self,
            prompt: str,
            *,
            model_name: str | None,
            metadata: dict[str, Any] | None,
            reasoning_effort: str | None = None,
            verbosity: str | None = None,
        ) -> dict[str, Any]:
            metadata = metadata or {}
            response = sk_text_adapter.invoke_text(
                prompt_text=prompt,
                model_preference=model_name,
                reasoning_effort=reasoning_effort or metadata.get("reasoning_effort"),
                verbosity=verbosity or metadata.get("verbosity"),
                response_token_budget=metadata.get("response_token_budget"),
            )
            text = str(response.get("text", "")).strip()
            if not text:
                raise ValidationError(
                    message="Azure OpenAI returned empty content.",
                    error_code="GENERATION_RESULT_INVALID",
                )
            usage = response.get("usage", {})
            prompt_tokens = (
                usage.get("prompt_tokens")
                if isinstance(usage, dict)
                else None
            )
            completion_tokens = (
                usage.get("completion_tokens")
                if isinstance(usage, dict)
                else None
            )
            total_tokens = (
                usage.get("total_tokens")
                if isinstance(usage, dict)
                else None
            )
            return {
                "text": text,
                "model": response.get("model", deployment),
                "usage": usage if isinstance(usage, dict) else {},
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "metadata": metadata,
            }

        def generate_text(
            self,
            prompt: str,
            *,
            model_name: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return self._call(
                prompt,
                model_name=model_name,
                metadata=metadata,
                reasoning_effort="medium",
                verbosity="medium",
            )

        def generate_table(
            self,
            prompt: str,
            *,
            model_name: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return self._call(
                prompt,
                model_name=model_name,
                metadata=metadata,
                reasoning_effort="low",
                verbosity="low",
            )

        def generate_puml(
            self,
            prompt: str,
            *,
            model_name: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            puml_prompt = (
                "Return only valid PlantUML source for the requested diagram. "
                "Do not add markdown fences.\n\n"
                f"{prompt}"
            )
            return self._call(
                puml_prompt,
                model_name=model_name,
                metadata=metadata,
                reasoning_effort="high",
                verbosity="low",
            )

        def correct_output(
            self,
            prompt: str,
            *,
            model_name: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return self._call(
                prompt,
                model_name=model_name,
                metadata=metadata,
                reasoning_effort="medium",
                verbosity="low",
            )

        def repair_puml(
            self,
            prompt: str,
            *,
            model_name: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return self.generate_puml(prompt, model_name=model_name, metadata=metadata)

    class _DiagramRenderer:
        def __init__(self, base_url: str) -> None:
            self._client = KrokiClientService(base_url=base_url)

        def render(self, puml_text: str) -> dict[str, Any]:
            png = self._client.render(puml_text, output_format=KrokiOutputFormat.PNG)
            svg = self._client.render(puml_text, output_format=KrokiOutputFormat.SVG)
            success = bool(png.success or svg.success)
            return {
                "success": success,
                "svg_content": svg.svg_content if svg.success else None,
                "png_content": png.png_content if png.success else None,
                "error_message": None if success else (png.error_message or svg.error_message),
            }

    class _RetrievalExecutor:
        def __init__(self, retrieval_payload: dict[str, Any]) -> None:
            self._payload = retrieval_payload

        def retrieve(
            self,
            *,
            section_id: str,
            section_heading: str,
            strategy: Any,
            retrieval_context: dict[str, Any] | None = None,
        ) -> Any:
            _ = (section_heading, strategy, retrieval_context)
            return RetrievalExecutionResult(
                retrieval_id=str(self._payload.get("retrieval_id", f"ret_{section_id}")),
                retrieval_status=str(self._payload.get("status", "OK")),
                diagnostics=self._payload.get("diagnostics", {}),
                source_evidence=_coerce_source_evidence(self._payload.get("evidence_bundle")),
                guideline_evidence=_coerce_guideline_evidence(self._payload.get("evidence_bundle")),
                exemplar_evidence=[],
                table_evidence=_coerce_table_evidence(self._payload.get("evidence_bundle")),
                conflict_evidence=_coerce_conflict_evidence(self._payload.get("evidence_bundle")),
            )

    def _to_dict(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if is_dataclass(value):
            return asdict(value)
        return {}

    def _bundle_dict(evidence_bundle: Any) -> dict[str, Any]:
        return _to_dict(evidence_bundle)

    def _safe_ref(item: dict[str, Any]) -> str | None:
        refs = item.get("refs") or []
        if refs and isinstance(refs, list):
            first = refs[0]
            if isinstance(first, dict):
                return first.get("chunk_id") or first.get("section_id")
        return None

    def _coerce_source_evidence(evidence_bundle: Any) -> list[Any]:
        bundle = _bundle_dict(evidence_bundle)
        source = _to_dict(bundle.get("source"))
        facts = source.get("facts") or []
        result = []
        for idx, fact in enumerate(facts):
            f = _to_dict(fact)
            text = str(f.get("text", "")).strip()
            if not text:
                continue
            result.append(
                EvidenceTextItem(
                    text=text,
                    confidence=float(f.get("confidence", 0.0) or 0.0),
                    source_ref=_safe_ref(f) or f"source_{idx}",
                    metadata={"requirement_ids": f.get("requirement_ids", [])},
                )
            )
        return result

    def _coerce_guideline_evidence(evidence_bundle: Any) -> list[Any]:
        bundle = _bundle_dict(evidence_bundle)
        guideline = _to_dict(bundle.get("guideline"))
        items = guideline.get("items") or []
        result = []
        for idx, item in enumerate(items):
            g = _to_dict(item)
            text = str(g.get("text", "")).strip()
            if not text:
                continue
            result.append(
                EvidenceTextItem(
                    text=text,
                    confidence=float(g.get("confidence", 0.0) or 0.0),
                    source_ref=_safe_ref(g) or f"guideline_{idx}",
                    metadata={},
                )
            )
        return result

    def _coerce_table_evidence(evidence_bundle: Any) -> list[Any]:
        bundle = _bundle_dict(evidence_bundle)
        source = _to_dict(bundle.get("source"))
        tables = source.get("tables") or []
        result = []
        for idx, table in enumerate(tables):
            t = _to_dict(table)
            headers = t.get("headers") or []
            rows = t.get("rows") or []
            lines: list[str] = []
            if headers:
                lines.append("| " + " | ".join(str(h) for h in headers) + " |")
                lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for row in rows:
                if isinstance(row, list):
                    lines.append("| " + " | ".join(str(c) for c in row) + " |")
            markdown = "\n".join(lines).strip() or str(t.get("title") or "")
            if not markdown:
                continue
            result.append(
                TableEvidenceItem(
                    table_markdown=markdown,
                    confidence=float(t.get("confidence", 0.0) or 0.0),
                    source_ref=_safe_ref(t) or f"table_{idx}",
                )
            )
        return result

    def _coerce_conflict_evidence(evidence_bundle: Any) -> list[Any]:
        bundle = _bundle_dict(evidence_bundle)
        source = _to_dict(bundle.get("source"))
        conflicts = source.get("conflicts") or []
        result = []
        for idx, conflict in enumerate(conflicts):
            c = _to_dict(conflict)
            desc = str(c.get("description", "")).strip()
            if not desc:
                continue
            result.append(
                ConflictEvidenceItem(
                    description=desc,
                    confidence=float(c.get("confidence", 0.0) or 0.0),
                    source_ref=_safe_ref(c) or f"conflict_{idx}",
                )
            )
        return result

    async def _runner(
        *,
        section_id: str,
        title: str,
        generation_strategy: str,
        retrieval_result: dict[str, Any],
        workflow_run_id: str | None = None,
        document_id: str | None = None,
        template_id: str | None = None,
        template_version: str | None = None,
        dependencies: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        _ = dependencies
        llm_backend = _LLMBackend()
        config = DEFAULT_GENERATION_CONFIG
        prompt_assembler = PromptAssembler(config=config)
        validator = OutputValidator()
        correction_loop = CorrectionLoop(
            validator=validator,
            backend=llm_backend,
            config=config,
        )
        diagram_renderer = _DiagramRenderer(
            base_url=os.getenv("KROKI_BASE_URL", "http://localhost:8000")
        )
        normalizer = PlantUMLNormalizerService()
        plantuml_validator = PlantUMLValidatorService()
        repair_loop = DiagramRepairLoopService(
            backend=llm_backend,
            normalizer=normalizer,
            validator=plantuml_validator,
            renderer=diagram_renderer,
            max_retries=config.diagram_render_max_retries,
        )
        artifacts_dir = settings.outputs_path / "diagram_artifacts"
        diagram_generator = DiagramGenerator(
            source_backend=llm_backend,
            normalizer=normalizer,
            validator=plantuml_validator,
            renderer=diagram_renderer,
            repair_loop=repair_loop,
            artifact_store=DiagramArtifactStoreService(base_dir=artifacts_dir),
            embedder=DiagramEmbedderService(),
        )
        text_generator = TextGenerator(llm_backend)
        table_generator = TableGenerator(llm_backend)
        sse_publisher = SSEPublisher()
        request_context_service = RequestContextService()
        pricing_registry_service = PricingRegistryService()
        cost_estimator_service = CostEstimatorService(pricing_registry_service=pricing_registry_service)
        cost_aggregation_service = CostAggregationService()
        logging_service = LoggingService(
            logger_name="observability.generation",
            context_provider=request_context_service.get_context_dict,
        )

        try:
            strategy = GenerationStrategy(generation_strategy)
        except Exception as exc:
            raise ValidationError(
                message=f"Unsupported generation strategy: {generation_strategy}",
                error_code="SECTION_GENERATION_INVALID",
                details={"section_id": section_id},
            ) from exc

        section_executor = SectionExecutor(
            retrieval_executor=_RetrievalExecutor(retrieval_result),
            prompt_assembler=prompt_assembler,
            text_generator=text_generator,
            table_generator=table_generator,
            diagram_generator=diagram_generator,
            output_validator=validator,
            correction_loop=correction_loop,
            sse_publisher=sse_publisher,
            logging_service=logging_service,
            request_context_service=request_context_service,
            cost_estimator_service=cost_estimator_service,
            cost_aggregation_service=cost_aggregation_service,
            config=config,
        )

        try:
            stable_job_id = (
                workflow_run_id
                or (metadata or {}).get("workflow_run_id")
                or (metadata or {}).get("job_id")
                or f"job_{generate_workflow_run_id()}"
            )
            execution_response = section_executor.execute(
                SectionExecutionRequest(
                    job_id=str(stable_job_id),
                    document_id=document_id or (metadata or {}).get("document_id"),
                    template_id=template_id or (metadata or {}).get("template_id"),
                    template_version=template_version or (metadata or {}).get("template_version"),
                    section_id=section_id,
                    section_heading=title,
                    strategy=strategy,
                    prompt_key=strategy.value,
                    dependencies_satisfied=True,
                    model_name=deployment,
                    retrieval_context={},
                    rolling_context=[],
                    metadata=metadata or {},
                )
            )
        except Exception as exc:
            raise ConfigurationError(
                message="SectionExecutor generation call failed.",
                error_code="GENERATION_RUNTIME_CALL_FAILED",
                details={"section_id": section_id, "reason": str(exc)},
            ) from exc

        result = execution_response.result
        status = (
            result.status.value
            if hasattr(result.status, "value")
            else str(result.status)
        )
        output_type = (
            result.output.output_type.value
            if result.output is not None
            else map_output_type(generation_strategy)
        )
        content = (
            result.output.content_markdown
            if result.output is not None
            else None
        )
        artifacts: list[dict[str, Any]] = []
        if result.output is not None and result.output.diagram_artifacts is not None:
            da = result.output.diagram_artifacts
            artifacts.append(
                {
                    "name": "diagram_manifest",
                    "manifest_path": da.manifest_path,
                    "puml_path": da.puml_path,
                    "svg_path": da.svg_path,
                    "png_path": da.png_path,
                }
            )
        if status in (
            SectionExecutionStatus.FAILED.value,
            SectionExecutionStatus.SKIPPED.value,
        ):
            raise ValidationError(
                message=result.error_message or "Section generation failed.",
                error_code="GENERATION_RESULT_INVALID",
                details={"section_id": section_id, "status": status},
            )

        return {
            "section_id": section_id,
            "generation_strategy": generation_strategy,
            "status": "COMPLETED",
            "output_type": output_type,
            "content": content,
            "artifacts": artifacts,
            "diagnostics": {
                "model": deployment,
                "source": "section_executor",
                "section_status": status,
                "issue_count": len(execution_response.validation_result.issues)
                if execution_response.validation_result
                else 0,
                "cost_metadata": execution_response.cost_metadata or {},
            },
            "warnings": [
                {"code": w.value if hasattr(w, "value") else str(w)}
                for w in (result.warnings or [])
            ],
            "errors": [],
        }

    return _runner
