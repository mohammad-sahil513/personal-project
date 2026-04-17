"""
Compiler orchestrator for custom template compilation.

This orchestrator combines:
- deterministic DOCX extraction,
- heuristic heading mapping,
- AI-assisted mapping fallback,
- defaults injection,
- semantic validation,
- bounded correction loop.

The orchestrator deliberately keeps business logic inside the Template module
and treats the AI/compiler adapter as an implementation detail underneath.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..contracts.compiler_contracts import (
    AICompilerSuggestion,
    DefaultsInjectionResult,
    ExtractedDocxStructure,
    HeuristicMappingResult,
    SemanticValidationResult,
)
from ..contracts.template_contracts import TemplateDefinition
from .ai_compiler import AICompiler
from .correction_loop import CorrectionLoop
from .defaults_injector import DefaultsInjector
from .docx_extractor import DocxExtractor
from .heuristic_mapper import HeuristicMapper
from .semantic_validator import SemanticValidator


@dataclass(frozen=True, slots=True)
class CompilerOrchestrationResult:
    """
    Final output of the custom template compiler orchestrator.
    """

    extracted_structure: ExtractedDocxStructure
    mapping_results: list[HeuristicMappingResult]
    ai_suggestions: list[AICompilerSuggestion]
    template_definition: TemplateDefinition
    defaults_injection_result: DefaultsInjectionResult
    semantic_validation_result: SemanticValidationResult
    correction_applied: bool
    correction_warnings: list[str]


class CompilerOrchestrator:
    """
    End-to-end orchestrator for deterministic + AI-assisted custom template compilation.
    """

    def __init__(
        self,
        *,
        docx_extractor: DocxExtractor | None = None,
        heuristic_mapper: HeuristicMapper | None = None,
        ai_compiler: AICompiler | None = None,
        defaults_injector: DefaultsInjector | None = None,
        semantic_validator: SemanticValidator | None = None,
        correction_loop: CorrectionLoop | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._docx_extractor = docx_extractor or DocxExtractor()
        self._heuristic_mapper = heuristic_mapper or HeuristicMapper()
        self._ai_compiler = ai_compiler or AICompiler()
        self._defaults_injector = defaults_injector or DefaultsInjector()
        self._semantic_validator = semantic_validator or SemanticValidator()
        self._correction_loop = correction_loop or CorrectionLoop(
            semantic_validator=self._semantic_validator
        )
        self._logger = logger or logging.getLogger(__name__)

    def compile_custom_template(
        self,
        *,
        docx_path: str,
        template_id: str,
        name: str,
        version: str,
        description: str | None = None,
        requirement_ids_filter_supported: bool = False,
    ) -> CompilerOrchestrationResult:
        """
        Compile a custom DOCX template into a normalized TemplateDefinition.
        """
        self._log_info(
            "compiler_orchestrator_start",
            docx_path=docx_path,
            template_id=template_id,
            template_version=version,
        )

        extracted_structure = self._docx_extractor.extract(docx_path)
        heuristic_results = self._heuristic_mapper.map_headings(extracted_structure.headings)
        ai_suggestions = self._ai_compiler.suggest_mappings(heuristic_results)
        merged_results = self._ai_compiler.apply_suggestions(
            mapping_results=heuristic_results,
            suggestions=ai_suggestions,
        )

        section_seeds = self._defaults_injector.build_section_seeds(
            headings=extracted_structure.headings,
            mapping_results=merged_results,
        )
        template_definition, defaults_result = self._defaults_injector.inject_defaults(
            template_id=template_id,
            name=name,
            version=version,
            description=description,
            section_seeds=section_seeds,
        )

        semantic_result = self._semantic_validator.validate_compiled_template(
            template_definition,
            requirement_ids_filter_supported=requirement_ids_filter_supported,
        )

        correction_applied = False
        correction_warnings: list[str] = []

        if not semantic_result.is_valid:
            corrected_definition, correction_result = self._correction_loop.correct_template(
                template_definition,
                requirement_ids_filter_supported=requirement_ids_filter_supported,
            )
            template_definition = corrected_definition
            correction_applied = correction_result.corrected
            correction_warnings = list(correction_result.warnings)

            semantic_result = self._semantic_validator.validate_compiled_template(
                template_definition,
                requirement_ids_filter_supported=requirement_ids_filter_supported,
            )

        self._log_info(
            "compiler_orchestrator_completed",
            template_id=template_id,
            template_version=version,
            extracted_heading_count=len(extracted_structure.headings),
            ai_suggestion_count=len(ai_suggestions),
            final_is_valid=semantic_result.is_valid,
            correction_applied=correction_applied,
        )

        return CompilerOrchestrationResult(
            extracted_structure=extracted_structure,
            mapping_results=merged_results,
            ai_suggestions=ai_suggestions,
            template_definition=template_definition,
            defaults_injection_result=defaults_result,
            semantic_validation_result=semantic_result,
            correction_applied=correction_applied,
            correction_warnings=correction_warnings,
        )

    def _log_info(self, event_name: str, **payload: object) -> None:
        """Emit a lightweight structured-ish log entry."""
        self._logger.info("%s | %s", event_name, payload)