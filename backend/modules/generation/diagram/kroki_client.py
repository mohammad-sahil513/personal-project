"""
Kroki client for the Generation module diagram runtime.

Responsibilities:
- Render validated PlantUML source through a Kroki endpoint
- Support svg and png output formats
- Return a structured render result for downstream orchestration

Important:
- This file is render-only.
- It does NOT normalize, validate, repair, store, or embed artifacts.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


@runtime_checkable
class HttpResponseProtocol(Protocol):
    """
    Minimal response protocol expected from the injected HTTP session.
    """

    @property
    def status_code(self) -> int:
        ...

    @property
    def text(self) -> str:
        ...

    @property
    def content(self) -> bytes:
        ...

    @property
    def reason(self) -> str:
        ...


@runtime_checkable
class HttpSessionProtocol(Protocol):
    """
    Minimal HTTP session protocol required by KrokiClientService.

    This keeps the client testable and avoids hard-coding a concrete HTTP library
    into the service contract.
    """

    def post(
        self,
        url: str,
        *,
        data: bytes,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> HttpResponseProtocol:
        ...


class KrokiOutputFormat(str, Enum):
    """
    Supported Kroki output formats used by the Generation module.
    """

    SVG = "svg"
    PNG = "png"


class KrokiRenderResult(BaseModel):
    """
    Structured render result returned by the Kroki client.
    """

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(description="Whether Kroki render succeeded.")
    output_format: KrokiOutputFormat = Field(
        description="Requested render output format."
    )
    svg_content: str | None = Field(
        default=None,
        description="Rendered SVG content when output_format=svg and render succeeds.",
    )
    png_content: bytes | None = Field(
        default=None,
        description="Rendered PNG bytes when output_format=png and render succeeds.",
    )
    status_code: int | None = Field(
        default=None,
        description="HTTP status code returned by Kroki, if available.",
    )
    error_message: str | None = Field(
        default=None,
        description="Failure detail if render did not succeed.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional transport/render metadata.",
    )


class KrokiClientService:
    """
    Render validated PlantUML source via a Kroki endpoint.

    Endpoint pattern used:
        {base_url}/plantuml/{format}

    Request body:
        raw PlantUML text, UTF-8 encoded
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 20.0,
        session: HttpSessionProtocol | None = None,
    ) -> None:
        if not base_url or not base_url.strip():
            raise ValueError("base_url cannot be empty.")

        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = session or self._build_default_session()

    def render(
        self,
        puml_text: str,
        output_format: KrokiOutputFormat = KrokiOutputFormat.PNG,
    ) -> KrokiRenderResult:
        """
        Render PlantUML source to the requested Kroki output format.
        """
        if puml_text is None:
            raise ValueError("puml_text cannot be None.")

        if not puml_text.strip():
            raise ValueError("puml_text cannot be empty.")

        if output_format not in {KrokiOutputFormat.SVG, KrokiOutputFormat.PNG}:
            raise ValueError(f"Unsupported Kroki output format: {output_format!r}")

        url = f"{self.base_url}/plantuml/{output_format.value}"
        payload = puml_text.encode("utf-8")
        headers = {
            "Content-Type": "text/plain; charset=utf-8",
            "Accept": self._accept_header_for(output_format),
        }

        try:
            response = self.session.post(
                url,
                data=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - exact exception type depends on HTTP library
            return KrokiRenderResult(
                success=False,
                output_format=output_format,
                status_code=None,
                error_message=f"Kroki request failed: {exc}",
                metadata={"url": url},
            )

        if 200 <= response.status_code < 300:
            if output_format == KrokiOutputFormat.SVG:
                return KrokiRenderResult(
                    success=True,
                    output_format=output_format,
                    svg_content=response.content.decode("utf-8", errors="replace"),
                    png_content=None,
                    status_code=response.status_code,
                    error_message=None,
                    metadata={"url": url},
                )

            return KrokiRenderResult(
                success=True,
                output_format=output_format,
                svg_content=None,
                png_content=response.content,
                status_code=response.status_code,
                error_message=None,
                metadata={"url": url},
            )

        error_detail = response.text.strip() or response.reason or "Unknown Kroki render failure"
        return KrokiRenderResult(
            success=False,
            output_format=output_format,
            svg_content=None,
            png_content=None,
            status_code=response.status_code,
            error_message=f"Kroki render failed ({response.status_code}): {error_detail}",
            metadata={"url": url},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _accept_header_for(self, output_format: KrokiOutputFormat) -> str:
        if output_format == KrokiOutputFormat.SVG:
            return "image/svg+xml"
        return "image/png"

    def _build_default_session(self) -> HttpSessionProtocol:
        """
        Build the default HTTP session lazily.

        `requests` is imported only when needed so the service remains easy to test
        with a fake/injected session.
        """
        try:
            import requests  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "requests is required for KrokiClientService default session construction."
            ) from exc

        return requests.Session()