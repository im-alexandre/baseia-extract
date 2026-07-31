from __future__ import annotations

import json
import mimetypes
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .identity import normalize_relative_path
from .layout import DocumentLayout, document_layout
from .storage import file_sha256


def document_storage_keys(
    row: Mapping[str, Any],
) -> tuple[str, str]:
    slug = str(row.get("collection_slug") or "").strip()
    relative = str(
        row.get("collection_relative_path")
        or row.get("relative_path")
        or ""
    )
    if not slug:
        raise ValueError("Documento sem collection_slug.")
    relative_path = PurePosixPath(normalize_relative_path(relative))
    source_key = normalize_relative_path(f"{slug}/{relative_path.as_posix()}")
    parent = (
        ""
        if relative_path.parent == PurePosixPath(".")
        else f"{relative_path.parent.as_posix()}/"
    )
    artifact_prefix = normalize_relative_path(
        f"{slug}/{parent}{relative_path.stem}"
    )
    return source_key, artifact_prefix


def _kind(relative: str) -> tuple[str, bool]:
    path = PurePosixPath(relative)
    if relative == "canonical/document.md":
        return "canonical_markdown", True
    if relative == "canonical/document_ir.json":
        return "canonical_document_ir", True
    if relative == "canonical/structure.json":
        return "canonical_structure", True
    if relative == "canonical/metadata.json":
        return "canonical_document_metadata", True
    if relative == "canonical/render.json":
        return "canonical_render_manifest", True
    if relative.startswith("canonical/chunks/") and relative.endswith(
        ".jsonl"
    ):
        return "canonical_chunks", True
    if relative.startswith("canonical/ingest/") and relative.endswith(
        ".json"
    ):
        return "canonical_ingest_manifest", True
    if relative.endswith("_middle.json"):
        return "mineru_middle_json", False
    if relative.endswith(("_content_list.json", "_content_list_v2.json")):
        return "mineru_content_list", False
    if path.suffix.casefold() == ".md":
        return "mineru_markdown", False
    if path.suffix.casefold() in {".jpg", ".jpeg", ".png", ".webp"}:
        return "mineru_image", False
    if path.name == "service.json":
        return "mineru_service_manifest", False
    if path.suffix.casefold() == ".pdf":
        return "mineru_pdf", False
    return "mineru_artifact", False


def _operational_file(relative: str) -> bool:
    path = PurePosixPath(relative)
    return (
        any(
            part.startswith(".")
            or part.casefold()
            in {"__pycache__", "migration-journal", "bootstrap-journal"}
            for part in path.parts
        )
        or path.name.casefold().endswith((".tmp", ".lock", ".bootstrap"))
    )


def artifact_records(
    row: Mapping[str, Any],
    *,
    origin: str,
    stage_run_id: str | None = None,
) -> list[dict[str, Any]]:
    layout = document_layout(row)
    source_key, artifact_prefix = document_storage_keys(row)
    records: list[dict[str, Any]] = []
    if not layout.pdf_path.is_file():
        raise FileNotFoundError(layout.pdf_path)
    records.append(
        {
            "kind": "source_pdf",
            "local_path": str(layout.pdf_path),
            "object_key": source_key,
            "sha256": file_sha256(layout.pdf_path),
            "bytes": layout.pdf_path.stat().st_size,
            "content_type": "application/pdf",
            "canonical": True,
            "origin": origin,
            "stage_run_id": stage_run_id,
        }
    )
    if layout.document_dir.is_dir():
        for path in sorted(layout.document_dir.rglob("*")):
            if not path.is_file() or path == layout.manifest_path:
                continue
            relative = path.relative_to(layout.document_dir).as_posix()
            if _operational_file(relative):
                continue
            kind, canonical = _kind(relative)
            records.append(
                {
                    "kind": kind,
                    "local_path": str(path),
                    "object_key": normalize_relative_path(
                        f"{artifact_prefix}/{relative}"
                    ),
                    "sha256": file_sha256(path),
                    "bytes": path.stat().st_size,
                    "content_type": (
                        mimetypes.guess_type(path.name)[0]
                        or "application/octet-stream"
                    ),
                    "canonical": canonical,
                    "origin": origin,
                    "stage_run_id": stage_run_id,
                }
            )
    return records


def build_document_manifest(
    row: Mapping[str, Any],
    *,
    origin: str,
    stage_runs: list[dict[str, Any]] | None = None,
    stage_run_id: str | None = None,
    replace_object_keys: set[str] | None = None,
    existing_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    layout: DocumentLayout = document_layout(row)
    source_key, artifact_prefix = document_storage_keys(row)
    sha256 = str(row["sha256"]).casefold()
    artifacts_with_paths = artifact_records(
        row,
        origin=origin,
        stage_run_id=stage_run_id,
    )
    artifacts = [
        {
            key: value
            for key, value in artifact.items()
            if key != "local_path"
        }
        for artifact in artifacts_with_paths
    ]
    if artifacts[0]["sha256"] != sha256:
        raise ValueError(
            f"SHA-256 do PDF divergiu do inventário: {layout.pdf_path}"
        )
    if (
        existing_manifest is not None
        and existing_manifest.get("schema_version") == 2
    ):
        replaced = replace_object_keys or set()
        existing_artifacts = {
            str(item.get("object_key")): item
            for item in existing_manifest.get("artifacts", [])
            if isinstance(item, dict) and item.get("object_key")
        }
        for artifact in artifacts:
            if artifact["object_key"] in replaced:
                continue
            previous = existing_artifacts.get(str(artifact["object_key"]))
            if (
                previous is None
                or previous.get("sha256") != artifact["sha256"]
                or int(previous.get("bytes", -1)) != artifact["bytes"]
            ):
                continue
            previous_origin = str(previous.get("origin") or origin)
            artifact["origin"] = previous_origin
            artifact["stage_run_id"] = previous.get("stage_run_id")
            if (
                previous_origin == origin
                and not artifact["stage_run_id"]
                and stage_run_id
            ):
                artifact["stage_run_id"] = stage_run_id
    if stage_runs is not None:
        resolved_stage_runs = list(stage_runs)
    elif (
        existing_manifest is not None
        and isinstance(existing_manifest.get("stage_runs"), list)
    ):
        resolved_stage_runs = [
            dict(item)
            for item in existing_manifest["stage_runs"]
            if isinstance(item, Mapping)
        ]
    else:
        resolved_stage_runs = []
    payload = {
        "schema_version": 2,
        "origin": origin,
        "collection": str(row["collection"]),
        "collection_slug": str(row["collection_slug"]),
        "document_id": str(row["document_id"]),
        "revision_id": str(row["revision_id"]),
        "sha256": sha256,
        "relative_path": layout.relative_pdf_path.as_posix(),
        "filename": layout.pdf_path.name,
        "source_object_key": source_key,
        "artifact_prefix": artifact_prefix,
        "artifacts": artifacts,
        "stage_runs": resolved_stage_runs,
    }
    if (
        existing_manifest is not None
        and existing_manifest.get("schema_version") == 2
    ):
        return {
            **dict(existing_manifest),
            **payload,
        }
    return payload


def serialize_document_manifest(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        # Windows não permite abrir diretórios em todas as configurações.
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def write_document_manifest_payload(
    row: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> Path:
    layout = document_layout(row)
    layout.document_dir.mkdir(parents=True, exist_ok=True)
    if str(payload.get("document_id") or "") != str(row["document_id"]):
        raise ValueError("Manifest pertence a outro documento.")
    if str(payload.get("revision_id") or "") != str(row["revision_id"]):
        raise ValueError("Manifest pertence a outra revisão.")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{layout.manifest_path.name}.",
        suffix=".tmp",
        dir=layout.document_dir,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(serialize_document_manifest(payload))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, layout.manifest_path)
        _fsync_directory(layout.document_dir)
    finally:
        temporary.unlink(missing_ok=True)
    return layout.manifest_path


def write_document_manifest(
    row: Mapping[str, Any],
    *,
    origin: str,
    stage_runs: list[dict[str, Any]] | None = None,
    stage_run_id: str | None = None,
    replace_object_keys: set[str] | None = None,
    existing_manifest: Mapping[str, Any] | None = None,
) -> Path:
    payload = build_document_manifest(
        row,
        origin=origin,
        stage_runs=stage_runs,
        stage_run_id=stage_run_id,
        replace_object_keys=replace_object_keys,
        existing_manifest=existing_manifest,
    )
    return write_document_manifest_payload(row, payload)
