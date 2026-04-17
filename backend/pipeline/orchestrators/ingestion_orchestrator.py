"""
Ingestion orchestrator.

This orchestrator wires the locked 9-stage ingestion flow into one execution path:

1. upload & dedup
2. parse document
3. PII masking
4. image classification
5. vision extraction
6. section segmentation
7. validation
8. semantic chunking
9. vector indexing

Part 1 scope:
- duplicate short-circuit handling
- validation-blocked stop handling
- Stage 5 -> Stage 6 convergence (vision-enriched markdown path)
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.ingestion.contracts.stage_1_contracts import Stage1Input, Stage1Output
from backend.modules.ingestion.contracts.stage_2_contracts import Stage2Input, Stage2Output
from backend.modules.ingestion.contracts.stage_3_contracts import Stage3Input, Stage3Output
from backend.modules.ingestion.contracts.stage_4_contracts import Stage4Input, Stage4Output
from backend.modules.ingestion.contracts.stage_5_contracts import Stage5Input, Stage5Output
from backend.modules.ingestion.contracts.stage_6_contracts import Stage6Input, Stage6Output
from backend.modules.ingestion.contracts.stage_7_contracts import Stage7Input, Stage7Output
from backend.modules.ingestion.contracts.stage_8_contracts import Stage8Input, Stage8Output
from backend.modules.ingestion.contracts.stage_9_contracts import Stage9Input, Stage9Output


class IngestionPipelineStatus(str, Enum):
    """High-level final status returned by the ingestion orchestrator."""

    COMPLETED = "COMPLETED"
    DUPLICATE_SKIPPED = "DUPLICATE_SKIPPED"
    VALIDATION_BLOCKED = "VALIDATION_BLOCKED"


class IngestionRunConfig(BaseModel):
    """Runtime options for the ingestion orchestrator."""

    model_config = ConfigDict(extra="forbid")

    pii_enabled: bool = True
    system_email_allowlist: list[str] = Field(default_factory=list)
    max_vision_calls: int = Field(default=10, ge=1, le=100)
    short_circuit_on_duplicate: bool = True


class IngestionPipelineResult(BaseModel):
    """
    Aggregated result of one orchestrated ingestion run.

    Some stage outputs remain optional because the pipeline may stop early
    on duplicate short-circuit or Stage 7 validation block.
    """

    model_config = ConfigDict(extra="forbid")

    status: IngestionPipelineStatus

    stage_1_output: Stage1Output
    stage_2_output: Stage2Output | None = None
    stage_3_output: Stage3Output | None = None
    stage_4_output: Stage4Output | None = None
    stage_5_output: Stage5Output | None = None
    stage_6_output: Stage6Output | None = None
    stage_7_output: Stage7Output | None = None
    stage_8_output: Stage8Output | None = None
    stage_9_output: Stage9Output | None = None


class Stage1RunnerProtocol(Protocol):
    async def run(self, request: Stage1Input) -> Stage1Output: ...


class Stage2RunnerProtocol(Protocol):
    async def run(self, request: Stage2Input) -> Stage2Output: ...


class Stage3RunnerProtocol(Protocol):
    async def run(self, request: Stage3Input) -> Stage3Output: ...


class Stage4RunnerProtocol(Protocol):
    async def run(self, request: Stage4Input) -> Stage4Output: ...


class Stage5RunnerProtocol(Protocol):
    async def run(self, request: Stage5Input) -> Stage5Output: ...


class Stage6RunnerProtocol(Protocol):
    async def run(self, request: Stage6Input) -> Stage6Output: ...


class Stage7RunnerProtocol(Protocol):
    async def run(self, request: Stage7Input) -> Stage7Output: ...


class Stage8RunnerProtocol(Protocol):
    async def run(self, request: Stage8Input) -> Stage8Output: ...


class Stage9RunnerProtocol(Protocol):
    async def run(self, request: Stage9Input) -> Stage9Output: ...


class IngestionOrchestrator:
    """Primary orchestrator for the locked ingestion pipeline."""

    def __init__(
        self,
        *,
        stage_1_runner: Stage1RunnerProtocol,
        stage_2_runner: Stage2RunnerProtocol,
        stage_3_runner: Stage3RunnerProtocol,
        stage_4_runner: Stage4RunnerProtocol,
        stage_5_runner: Stage5RunnerProtocol,
        stage_6_runner: Stage6RunnerProtocol,
        stage_7_runner: Stage7RunnerProtocol,
        stage_8_runner: Stage8RunnerProtocol,
        stage_9_runner: Stage9RunnerProtocol,
    ) -> None:
        self._stage_1_runner = stage_1_runner
        self._stage_2_runner = stage_2_runner
        self._stage_3_runner = stage_3_runner
        self._stage_4_runner = stage_4_runner
        self._stage_5_runner = stage_5_runner
        self._stage_6_runner = stage_6_runner
        self._stage_7_runner = stage_7_runner
        self._stage_8_runner = stage_8_runner
        self._stage_9_runner = stage_9_runner

    async def run(
        self,
        *,
        stage_1_input: Stage1Input,
        config: IngestionRunConfig | None = None,
    ) -> IngestionPipelineResult:
        """Execute the full ingestion pipeline in locked stage order."""
        run_config = config or IngestionRunConfig()

        stage_1_output = await self._stage_1_runner.run(stage_1_input)
        if stage_1_output.is_duplicate and run_config.short_circuit_on_duplicate:
            return IngestionPipelineResult(
                status=IngestionPipelineStatus.DUPLICATE_SKIPPED,
                stage_1_output=stage_1_output,
            )

        stage_2_output = await self._stage_2_runner.run(
            Stage2Input.from_stage_1_output(stage_1_output)
        )

        stage_3_output = await self._stage_3_runner.run(
            Stage3Input.from_stage_2_output(
                stage_2_output,
                pii_enabled=run_config.pii_enabled,
                system_email_allowlist=run_config.system_email_allowlist,
            )
        )

        stage_4_output = await self._stage_4_runner.run(
            Stage4Input.from_stage_3_output(stage_3_output)
        )

        stage_5_output = await self._stage_5_runner.run(
            Stage5Input.from_stage_4_output(
                stage_4_output,
                max_vision_calls=run_config.max_vision_calls,
            )
        )

        # Convergence point:
        # Stage 6 should now consume the Stage 5 vision-enriched markdown path.
        stage_6_output = await self._stage_6_runner.run(
            Stage6Input.from_stage_5_output(stage_5_output)
        )

        stage_7_output = await self._stage_7_runner.run(
            Stage7Input.from_stage_6_output(
                stage_6_output,
                parse_quality_report=stage_5_output.parse_quality_report,
                asset_registry=stage_5_output.asset_registry,
                pii_enabled=run_config.pii_enabled,
                pii_mapping_blob_path=(
                    stage_3_output.secure_mapping_artifact.blob_path
                    if stage_3_output.secure_mapping_artifact
                    else None
                ),
                mapped_pii_values=[],
                allowlisted_system_emails=run_config.system_email_allowlist,
            )
        )

        if not stage_7_output.summary.can_proceed_to_chunking:
            return IngestionPipelineResult(
                status=IngestionPipelineStatus.VALIDATION_BLOCKED,
                stage_1_output=stage_1_output,
                stage_2_output=stage_2_output,
                stage_3_output=stage_3_output,
                stage_4_output=stage_4_output,
                stage_5_output=stage_5_output,
                stage_6_output=stage_6_output,
                stage_7_output=stage_7_output,
            )

        stage_8_output = await self._stage_8_runner.run(
            Stage8Input.from_stage_7_output(stage_7_output)
        )

        stage_9_output = await self._stage_9_runner.run(
            Stage9Input.from_stage_8_output(stage_8_output)
        )

        return IngestionPipelineResult(
            status=IngestionPipelineStatus.COMPLETED,
            stage_1_output=stage_1_output,
            stage_2_output=stage_2_output,
            stage_3_output=stage_3_output,
            stage_4_output=stage_4_output,
            stage_5_output=stage_5_output,
            stage_6_output=stage_6_output,
            stage_7_output=stage_7_output,
            stage_8_output=stage_8_output,
            stage_9_output=stage_9_output,
        )