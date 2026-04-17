"""
Optional Azure Blob publisher for Template artifacts.

This service uploads already-persisted local Template artifacts to the shared
Blob container under the required root prefix:
    sahil_storage/

It intentionally does not replace local persistence. Instead, it publishes the
local files produced by TemplateArtifactService so the smoke run can validate:
- local artifact creation, and
- optional cloud artifact publication.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from backend.core.config import get_settings


@dataclass(frozen=True, slots=True)
class PublishedBlobArtifact:
    """Represents one uploaded blob artifact."""

    local_path: Path
    blob_path: str
    blob_url: str


class TemplateBlobPublisherService:
    """
    Upload Template artifacts to Azure Blob Storage.

    Supported authentication:
    - connection string (preferred if already configured in .env)
    - account URL + DefaultAzureCredential
    """

    def __init__(
        self,
        *,
        container_name: str | None = None,
        root_prefix: str | None = None,
        connection_string: str | None = None,
        account_url: str | None = None,
    ) -> None:
        settings = get_settings()
        self._container_name = container_name or settings.azure_storage_container_name
        resolved_root_prefix = root_prefix or settings.azure_storage_root_prefix_normalized
        self._root_prefix = resolved_root_prefix.strip("/")

        self._connection_string = (
            connection_string
            or settings.azure_storage_connection_string
        )
        self._account_url = (
            account_url
            or settings.azure_storage_account_url
        )

        if not self._container_name:
            raise ValueError("AZURE_STORAGE_CONTAINER_NAME is required for blob publishing.")

        if not self._connection_string and not self._account_url:
            raise ValueError(
                "Either AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_URL is required."
            )

    def publish_artifacts(
        self,
        *,
        template_id: str,
        version: str,
        artifacts: dict[str, Path],
        subfolder: str = "template/custom",
    ) -> dict[str, PublishedBlobArtifact]:
        """
        Upload a set of local artifact files to the shared container.

        Blob path shape:
            sahil_storage/template/custom/<template_id>/<version>/<filename>
        """
        container_client = self._get_container_client()
        published: dict[str, PublishedBlobArtifact] = {}

        for artifact_name, local_path in artifacts.items():
            resolved_path = local_path.resolve()
            if not resolved_path.exists():
                raise FileNotFoundError(f"Artifact file not found for blob upload: {resolved_path}")

            blob_path = (
                f"{self._root_prefix}/"
                f"{subfolder.strip('/')}/"
                f"{template_id}/"
                f"{version}/"
                f"{resolved_path.name}"
            )
            content_type = mimetypes.guess_type(resolved_path.name)[0] or "application/octet-stream"

            with resolved_path.open("rb") as handle:
                container_client.upload_blob(
                    name=blob_path,
                    data=handle,
                    overwrite=True,
                    content_settings=ContentSettings(content_type=content_type),
                )

            blob_url = f"{container_client.url}/{blob_path}"
            published[artifact_name] = PublishedBlobArtifact(
                local_path=resolved_path,
                blob_path=blob_path,
                blob_url=blob_url,
            )

        return published

    def _get_container_client(self):
        """Create a container client using the configured auth strategy."""
        if self._connection_string:
            blob_service_client = BlobServiceClient.from_connection_string(self._connection_string)
        else:
            blob_service_client = BlobServiceClient(
                account_url=self._account_url,
                credential=DefaultAzureCredential(),
            )

        return blob_service_client.get_container_client(self._container_name)