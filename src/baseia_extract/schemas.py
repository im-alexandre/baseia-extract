from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sha256: str
    document_id: str
    path: Path
    filename: str
    size_bytes: int | None = None
    page_count: int | None = None

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64:
            raise ValueError("sha256 deve conter 64 caracteres hexadecimais")
        try:
            bytes.fromhex(normalized)
        except ValueError as error:
            raise ValueError("sha256 inválido") from error
        return normalized


class ExtractionResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sha256: str
    document_id: str
    status: str
    output_dir: Path
    attempts: int = 0
    retry_count: int = 0
    pod_id: str | None = None
    api_url: str | None = None
    task_id: str | None = None
    correlation_key: str | None = None
    duration_seconds: float | None = None
    source_uri: str | None = None
    artifact_uri: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    task_history: list[dict[str, Any]] = Field(default_factory=list)
    throughput_eligible: bool = False
    error: str | None = None


class ExtractionManifest(BaseModel):
    """Estado durável e autocontido de uma extração por documento."""

    model_config = ConfigDict(extra="ignore")

    sha256: str
    document_id: str
    path: Path
    filename: str
    output_dir: Path
    service: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"
    attempts: int = 0
    retry_count: int = 0
    pod_id: str | None = None
    api_url: str | None = None
    task_id: str | None = None
    correlation_key: str | None = None
    duration_seconds: float | None = None
    source_uri: str | None = None
    artifact_uri: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    task_history: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    updated_at: str | None = None
    row: dict[str, Any] = Field(default_factory=dict)
    controller: dict[str, Any] = Field(default_factory=dict)
