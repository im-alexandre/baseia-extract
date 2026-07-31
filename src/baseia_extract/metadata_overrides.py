"""Decisões manuais, versionadas por coleção, para metadados bibliográficos."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .identity import canonical_json_sha256, normalize_relative_path
from .storage import file_sha256


MetadataOverrideSource = Literal[
    "first_page_author_block",
    "bibliographic_reference_or_synthetic_metadata_sheet",
    "institutional_or_contract",
]


class DocumentMetadataOverride(BaseModel):
    """Decisão humana para os autores de um PDF da coleção."""

    model_config = ConfigDict(extra="forbid")

    authors: list[str] = Field(default_factory=list)
    corporate_authors: list[str] = Field(default_factory=list)
    no_personal_author: bool = False
    source: MetadataOverrideSource
    note: str | None = None

    @field_validator("authors", "corporate_authors")
    @classmethod
    def names_are_nonempty_and_unique(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            name = " ".join(value.split())
            if not name:
                raise ValueError("nomes não podem ser vazios")
            key = name.casefold()
            if key in seen:
                raise ValueError("nomes não podem se repetir")
            seen.add(key)
            normalized.append(name)
        return normalized

    @field_validator("note")
    @classmethod
    def note_is_nonempty_when_present(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("note não pode ser vazia")
        return normalized

    @model_validator(mode="after")
    def is_an_actual_decision(self) -> DocumentMetadataOverride:
        if self.no_personal_author and self.authors:
            raise ValueError(
                "no_personal_author não pode ser usado com authors"
            )
        if not self.authors and not self.no_personal_author:
            raise ValueError(
                "corporate_authors sem authors exige "
                "no_personal_author=true"
            )
        if (
            self.source == "institutional_or_contract"
            and not self.no_personal_author
        ):
            raise ValueError(
                "institutional_or_contract exige no_personal_author=true"
            )
        if not (
            self.authors
            or self.corporate_authors
            or self.no_personal_author
        ):
            raise ValueError(
                "a decisão deve ter authors, corporate_authors ou "
                "no_personal_author=true"
            )
        return self


class MetadataOverrides(BaseModel):
    """Arquivo ``.baseia/metadata-overrides.yaml`` de uma coleção."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    documents: dict[str, DocumentMetadataOverride] = Field(
        default_factory=dict
    )

    @field_validator("documents")
    @classmethod
    def document_paths_are_canonical(
        cls,
        values: dict[str, DocumentMetadataOverride],
    ) -> dict[str, DocumentMetadataOverride]:
        normalized: dict[str, DocumentMetadataOverride] = {}
        for raw_path, decision in values.items():
            if not isinstance(raw_path, str):
                raise ValueError("as chaves de documents devem ser texto")
            path = normalize_relative_path(raw_path)
            if Path(path).suffix.casefold() != ".pdf":
                raise ValueError(
                    "as chaves de documents devem apontar para PDFs: "
                    f"{raw_path!r}"
                )
            if path != raw_path:
                raise ValueError(
                    "as chaves de documents devem usar caminhos relativos "
                    f"POSIX normalizados: {raw_path!r}"
                )
            if path in normalized:
                raise ValueError(f"documento repetido: {path!r}")
            normalized[path] = decision
        return normalized


class ResolvedMetadataOverride(BaseModel):
    """Decisão associada a um documento, com hashes para currentness."""

    model_config = ConfigDict(extra="forbid")

    path: str
    decision: DocumentMetadataOverride
    decision_sha256: str
    source_file_sha256: str


def metadata_overrides_path(collection_root: str | Path) -> Path:
    return (
        Path(collection_root).expanduser().resolve()
        / ".baseia"
        / "metadata-overrides.yaml"
    )


def load_metadata_overrides(
    collection_root: str | Path,
) -> tuple[MetadataOverrides, Path, str | None]:
    """Lê decisões da coleção; a ausência do arquivo representa zero overrides."""
    source = metadata_overrides_path(collection_root)
    if not source.is_file():
        return MetadataOverrides(), source, None
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"YAML inválido: {source}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"YAML deve conter um objeto na raiz: {source}")
    return (
        MetadataOverrides.model_validate(payload),
        source,
        file_sha256(source),
    )


def resolve_metadata_override(
    overrides: MetadataOverrides,
    *,
    relative_path: str,
    source_path: Path,
    source_file_sha256: str | None,
) -> ResolvedMetadataOverride | None:
    normalized_path = normalize_relative_path(relative_path)
    decision = overrides.documents.get(normalized_path)
    if decision is None:
        return None
    if source_file_sha256 is None:
        raise ValueError(
            "Decisão manual encontrada sem arquivo de origem: "
            f"{source_path}"
        )
    return ResolvedMetadataOverride(
        path=normalized_path,
        decision=decision,
        decision_sha256=canonical_json_sha256(
            decision.model_dump(mode="json")
        ),
        source_file_sha256=source_file_sha256,
    )


__all__ = [
    "DocumentMetadataOverride",
    "MetadataOverrides",
    "ResolvedMetadataOverride",
    "load_metadata_overrides",
    "resolve_metadata_override",
]
