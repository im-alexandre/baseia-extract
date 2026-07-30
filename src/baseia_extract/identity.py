from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

CATALOG_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://baseia.local/catalog/v1",
)


def collection_slug(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
    if not slug:
        raise ValueError("O nome da coleção não produz um slug válido.")
    return slug


def normalize_relative_path(value: str | PurePosixPath) -> str:
    raw = str(value).replace("\\", "/").strip("/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError(f"Caminho relativo inválido: {value!r}")
    return path.as_posix()


def collection_uuid(slug: str) -> uuid.UUID:
    return uuid.uuid5(CATALOG_NAMESPACE, f"collection:{collection_slug(slug)}")


def document_uuid(slug: str, relative_path: str | PurePosixPath) -> uuid.UUID:
    normalized_slug = collection_slug(slug)
    normalized_path = normalize_relative_path(relative_path)
    return uuid.uuid5(
        CATALOG_NAMESPACE,
        f"document:{normalized_slug}:{normalized_path}",
    )


def revision_uuid(document_id: uuid.UUID | str, sha256: str) -> uuid.UUID:
    digest = validate_sha256(sha256)
    return uuid.uuid5(uuid.UUID(str(document_id)), f"revision:{digest}")


def artifact_uuid(
    revision_id: uuid.UUID | str,
    object_key: str,
) -> uuid.UUID:
    key = normalize_relative_path(object_key)
    return uuid.uuid5(uuid.UUID(str(revision_id)), f"artifact:{key}")


def validate_sha256(value: str) -> str:
    normalized = value.strip().casefold()
    if len(normalized) != 64:
        raise ValueError("SHA-256 deve conter 64 caracteres hexadecimais.")
    try:
        bytes.fromhex(normalized)
    except ValueError as error:
        raise ValueError("SHA-256 inválido.") from error
    return normalized


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def stage_idempotency_key(
    *,
    revision_id: uuid.UUID | str,
    stage: str,
    processor: str,
    processor_version: str,
    config_hash: str,
    input_hashes: Iterable[str],
) -> str:
    normalized_inputs = sorted(validate_sha256(item) for item in input_hashes)
    return canonical_json_sha256(
        {
            "revision_id": str(uuid.UUID(str(revision_id))),
            "stage": stage.strip().casefold(),
            "processor": processor.strip().casefold(),
            "processor_version": processor_version.strip(),
            "config_hash": validate_sha256(config_hash),
            "input_hashes": normalized_inputs,
        }
    )
