from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ..identity import (
    collection_slug,
    collection_uuid,
    document_uuid,
    normalize_relative_path,
    revision_uuid,
    stage_idempotency_key,
    validate_sha256,
)

Sha256 = Annotated[str, Field(min_length=64, max_length=64)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ArtifactInput(StrictModel):
    id: uuid.UUID | None = None
    kind: str = Field(min_length=1, max_length=96)
    object_key: str = Field(min_length=1)
    checksum_sha256: Sha256
    size_bytes: int = Field(ge=0)
    content_type: str = Field(min_length=1, max_length=255)
    canonical: bool = False

    @field_validator("object_key")
    @classmethod
    def validate_object_key(cls, value: str) -> str:
        return normalize_relative_path(value)

    @field_validator("checksum_sha256")
    @classmethod
    def validate_checksum(cls, value: str) -> str:
        return validate_sha256(value)


class SnapshotCreate(StrictModel):
    id: uuid.UUID
    scope: str = Field(min_length=1, max_length=128)
    source: Literal["bootstrap", "s3_inventory"]
    manifest_key: str
    inventory_sha256: Sha256
    expected_document_count: int = Field(ge=0)
    expected_artifact_count: int = Field(ge=0)

    @field_validator("manifest_key")
    @classmethod
    def validate_manifest_key(cls, value: str) -> str:
        return normalize_relative_path(value)

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        return collection_slug(value)

    @field_validator("inventory_sha256")
    @classmethod
    def validate_inventory_hash(cls, value: str) -> str:
        return validate_sha256(value)


class SnapshotRead(StrictModel):
    id: uuid.UUID
    scope: str
    status: str
    source: str
    manifest_key: str
    inventory_sha256: str
    expected_document_count: int
    expected_artifact_count: int
    document_count: int | None
    artifact_count: int | None
    created_at: datetime
    activated_at: datetime | None


class BootstrapDocument(StrictModel):
    collection_id: uuid.UUID
    collection_slug: str = Field(min_length=1, max_length=96)
    collection_name: str = Field(min_length=1, max_length=255)
    collection_storage_prefix: str = Field(min_length=1)
    document_id: uuid.UUID
    revision_id: uuid.UUID
    relative_path: str
    filename: str
    sha256: Sha256
    size_bytes: int = Field(ge=0)
    source_object_key: str
    artifacts: list[ArtifactInput] = Field(default_factory=list)

    @field_validator(
        "collection_storage_prefix",
        "relative_path",
        "source_object_key",
    )
    @classmethod
    def validate_paths(cls, value: str) -> str:
        return normalize_relative_path(value)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        name = PurePosixPath(value).name
        if name != value or not name.casefold().endswith(".pdf"):
            raise ValueError("filename deve ser um nome de PDF, sem diretórios.")
        return name

    @field_validator("sha256")
    @classmethod
    def validate_document_hash(cls, value: str) -> str:
        return validate_sha256(value)

    @model_validator(mode="after")
    def validate_identity(self) -> BootstrapDocument:
        if self.collection_id != collection_uuid(self.collection_slug):
            raise ValueError("collection_id não corresponde ao slug.")
        if self.collection_storage_prefix != self.collection_slug:
            raise ValueError(
                "collection_storage_prefix deve ser o slug canônico."
            )
        expected_document_id = document_uuid(
            self.collection_slug,
            self.relative_path,
        )
        if self.document_id != expected_document_id:
            raise ValueError(
                "document_id não corresponde à coleção e ao path."
            )
        if self.revision_id != revision_uuid(self.document_id, self.sha256):
            raise ValueError(
                "revision_id não corresponde ao documento e ao SHA-256."
            )
        if PurePosixPath(self.relative_path).name != self.filename:
            raise ValueError("filename não corresponde ao relative_path.")
        expected_source_key = normalize_relative_path(
            f"{self.collection_slug}/{self.relative_path}"
        )
        if self.source_object_key != expected_source_key:
            raise ValueError("source_object_key não corresponde ao documento.")
        return self


class BootstrapBatch(StrictModel):
    documents: list[BootstrapDocument] = Field(min_length=1, max_length=250)


class SnapshotActivation(StrictModel):
    expected_document_count: int = Field(ge=0)
    expected_artifact_count: int = Field(ge=0)


class StageRunCreate(StrictModel):
    document_revision_id: uuid.UUID
    stage: str = Field(min_length=1, max_length=64)
    processor: str = Field(min_length=1, max_length=128)
    processor_version: str = Field(min_length=1, max_length=128)
    config_hash: Sha256
    input_hashes: list[Sha256] = Field(min_length=1)
    idempotency_key: Sha256
    lease_owner: str = Field(min_length=1, max_length=255)
    lease_seconds: int = Field(default=7200, ge=60, le=86400)

    @field_validator("config_hash", "idempotency_key")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        return validate_sha256(value)

    @field_validator("input_hashes")
    @classmethod
    def validate_inputs(cls, value: list[str]) -> list[str]:
        return sorted({validate_sha256(item) for item in value})

    @model_validator(mode="after")
    def validate_idempotency_contract(self) -> StageRunCreate:
        expected = stage_idempotency_key(
            revision_id=self.document_revision_id,
            stage=self.stage,
            processor=self.processor,
            processor_version=self.processor_version,
            config_hash=self.config_hash,
            input_hashes=self.input_hashes,
        )
        if self.idempotency_key != expected:
            raise ValueError(
                "idempotency_key não corresponde ao contrato do stage."
            )
        return self


class StageRunRead(StrictModel):
    id: uuid.UUID
    document_revision_id: uuid.UUID
    stage: str
    processor: str
    processor_version: str
    config_hash: str
    input_hashes: list[str]
    idempotency_key: str
    status: str
    attempt: int
    error: dict[str, object] | None
    lease_owner: str | None
    lease_until: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    artifacts: list[ArtifactInput] = Field(default_factory=list)
    created: bool = False
    claimed: bool = False


class StageRunStatusUpdate(StrictModel):
    status: Literal[
        "queued",
        "processing",
        "uploading",
        "cataloging",
        "cancelled",
        "orphaned",
    ]
    lease_owner: str = Field(min_length=1, max_length=255)
    lease_attempt: int = Field(ge=1)
    lease_seconds: int = Field(default=7200, ge=60, le=86400)


class StageRunHeartbeat(StrictModel):
    lease_owner: str = Field(min_length=1, max_length=255)
    lease_attempt: int = Field(ge=1)
    lease_seconds: int = Field(default=7200, ge=60, le=86400)


class StageRunComplete(StrictModel):
    artifacts: list[ArtifactInput] = Field(min_length=1)
    lease_owner: str = Field(min_length=1, max_length=255)
    lease_attempt: int = Field(ge=1)


class StageRunFail(StrictModel):
    error_type: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1)
    retryable: bool
    lease_owner: str = Field(min_length=1, max_length=255)
    lease_attempt: int = Field(ge=1)
