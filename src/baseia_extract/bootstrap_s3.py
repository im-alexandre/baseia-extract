from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
import uuid
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import httpx
import pandas as pd

from .document_manifest import document_storage_keys
from .identity import (
    CATALOG_NAMESPACE,
    artifact_uuid,
    collection_slug,
    collection_uuid,
    normalize_relative_path,
)
from .inventory_selection import physical_path_mask
from .layout import document_layout
from .settings import settings
from .storage import S3ArtifactStore, UploadRequest, file_sha256


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _manifest_artifacts(
    row: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[UploadRequest]]:
    layout = document_layout(row)
    payload = json.loads(layout.manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 2:
        raise ValueError(f"Manifesto v2 obrigatório: {layout.manifest_path}")
    if str(payload.get("sha256")) != str(row["sha256"]):
        raise ValueError(f"SHA divergente: {layout.manifest_path}")
    source_key, artifact_prefix = document_storage_keys(row)
    requests: list[UploadRequest] = []
    catalog: list[dict[str, Any]] = []
    declared = payload.get("artifacts")
    if not isinstance(declared, list):
        raise TypeError(f"Manifesto sem artifacts: {layout.manifest_path}")
    for artifact in declared:
        if not isinstance(artifact, dict):
            raise TypeError(f"Artifact inválido: {layout.manifest_path}")
        key = normalize_relative_path(str(artifact["object_key"]))
        if key == source_key:
            local_path = layout.pdf_path
        else:
            prefix = f"{artifact_prefix}/"
            if not key.startswith(prefix):
                raise ValueError(
                    f"Artifact fora do diretório do documento: {key}"
                )
            relative = PurePosixPath(key.removeprefix(prefix))
            local_path = layout.document_dir / Path(*relative.parts)
        if not local_path.is_file():
            raise FileNotFoundError(local_path)
        checksum = str(artifact["sha256"])
        if file_sha256(local_path) != checksum:
            raise ValueError(f"Artifact local divergiu: {local_path}")
        size_bytes = int(artifact["bytes"])
        if local_path.stat().st_size != size_bytes:
            raise ValueError(f"Tamanho local divergiu: {local_path}")
        content_type = str(
            artifact.get("content_type")
            or mimetypes.guess_type(local_path.name)[0]
            or "application/octet-stream"
        )
        requests.append(
            UploadRequest(
                source=local_path,
                key=key,
                sha256=checksum,
                content_type=content_type,
            )
        )
        catalog.append(
            {
                "id": str(artifact_uuid(row["revision_id"], key)),
                "kind": str(artifact["kind"]),
                "object_key": key,
                "checksum_sha256": checksum,
                "size_bytes": size_bytes,
                "content_type": content_type,
                "canonical": bool(artifact.get("canonical")),
            }
        )

    manifest_key = normalize_relative_path(
        f"{artifact_prefix}/manifest.json"
    )
    manifest_sha = file_sha256(layout.manifest_path)
    manifest_size = layout.manifest_path.stat().st_size
    requests.append(
        UploadRequest(
            source=layout.manifest_path,
            key=manifest_key,
            sha256=manifest_sha,
            content_type="application/json",
        )
    )
    catalog.append(
        {
            "id": str(artifact_uuid(row["revision_id"], manifest_key)),
            "kind": "document_manifest",
            "object_key": manifest_key,
            "checksum_sha256": manifest_sha,
            "size_bytes": manifest_size,
            "content_type": "application/json",
            "canonical": True,
        }
    )
    return catalog, requests


REQUIRED_INVENTORY_COLUMNS = {
    "collection",
    "collection_slug",
    "document_id",
    "revision_id",
    "sha256",
    "relative_path",
    "collection_relative_path",
    "filename",
    "size_bytes",
    "status",
}


def _collection_filters(values: Iterable[str] | str | None) -> tuple[str, ...]:
    if values is None:
        return ()
    candidates = (values,) if isinstance(values, str) else tuple(values)
    return tuple(
        dict.fromkeys(
            collection_slug(value)
            for value in candidates
            if str(value).strip()
        )
    )


def _inventory_source(value: str | Path | None) -> Path:
    if value is None or not str(value).strip():
        return settings.inventory_path
    return Path(value).expanduser().resolve()


def _snapshot_scope(
    requested: str,
    collection_slugs: set[str],
) -> str:
    if requested.strip():
        return collection_slug(requested)
    if len(collection_slugs) == 1:
        return next(iter(collection_slugs))
    raise ValueError(
        "O inventário contém mais de uma coleção. "
        "Informe --scope para definir qual snapshot ativo elas compõem."
    )


def _build_snapshot(
    *,
    inventory_path: str | Path | None = None,
    scope: str = "",
    collections: Iterable[str] | str | None = None,
    collection_path: str | Path | None = None,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[UploadRequest],
    bytes,
]:
    source_path = _inventory_source(inventory_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"Inventário não encontrado: {source_path}")
    inventory = pd.read_csv(
        source_path,
        dtype=str,
        keep_default_na=False,
    )
    missing_columns = REQUIRED_INVENTORY_COLUMNS.difference(
        inventory.columns
    )
    if missing_columns:
        raise ValueError(
            f"Colunas ausentes no inventário: {sorted(missing_columns)}"
        )
    selected = inventory.copy()
    filters = _collection_filters(collections)
    raw_collection_path = (
        str(collection_path).strip()
        if collection_path is not None
        else ""
    )
    if filters and raw_collection_path:
        raise ValueError(
            "Use somente um seletor: --collection ou --path."
        )
    if filters:
        available = {
            collection_slug(value)
            for value in selected["collection_slug"]
            if str(value).strip()
        }
        unavailable = set(filters).difference(available)
        if unavailable:
            raise ValueError(
                "Coleções ausentes no inventário: "
                f"{sorted(unavailable)}"
            )
        selected = selected[
            selected["collection_slug"].map(collection_slug).isin(filters)
        ].copy()
    elif raw_collection_path:
        if "path" not in selected.columns:
            raise ValueError(
                "O seletor --path exige a coluna path no inventário."
            )
        selected = selected.loc[
            physical_path_mask(
                selected["path"],
                raw_collection_path,
            )
        ].copy()
    if selected.empty:
        raise RuntimeError("Nenhum documento foi selecionado para promoção.")
    invalid = selected[~selected["status"].eq("ok")]
    if not invalid.empty:
        raise RuntimeError(
            "A promoção exige um inventário totalmente válido; "
            f"{len(invalid)} linha(s) têm status diferente de 'ok'."
        )
    for column in ("document_id", "revision_id"):
        duplicates = selected[
            selected[column].duplicated(keep=False)
        ]
        if not duplicates.empty:
            raise RuntimeError(
                f"Identidades duplicadas em {column}: "
                f"{sorted(duplicates[column].unique())[:5]}"
            )
    selected_slugs = {
        collection_slug(value)
        for value in selected["collection_slug"]
    }
    resolved_scope = _snapshot_scope(scope, selected_slugs)

    documents: list[dict[str, Any]] = []
    uploads: list[UploadRequest] = []
    keys: set[str] = set()
    for row in selected.sort_values("relative_path").to_dict(
        orient="records"
    ):
        artifacts, document_uploads = _manifest_artifacts(row)
        source_key, _ = document_storage_keys(row)
        for upload in document_uploads:
            if upload.key in keys:
                raise RuntimeError(f"Chave S3 duplicada: {upload.key}")
            keys.add(upload.key)
        uploads.extend(document_uploads)
        slug = collection_slug(str(row["collection_slug"]))
        documents.append(
            {
                "collection_id": str(collection_uuid(slug)),
                "collection_slug": slug,
                "collection_name": str(row["collection"]),
                "collection_storage_prefix": slug,
                "document_id": str(row["document_id"]),
                "revision_id": str(row["revision_id"]),
                "relative_path": str(
                    row["collection_relative_path"]
                ).replace("\\", "/"),
                "filename": str(row["filename"]),
                "sha256": str(row["sha256"]),
                "size_bytes": int(row["size_bytes"]),
                "source_object_key": source_key,
                "artifacts": artifacts,
            }
        )
    lines = [
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for document in documents
    ]
    inventory_payload = ("\n".join(lines) + "\n").encode("utf-8")
    inventory_sha = hashlib.sha256(inventory_payload).hexdigest()
    identity = (
        f"inventory-snapshot:{inventory_sha}"
        if resolved_scope == "default"
        else f"inventory-snapshot:{resolved_scope}:{inventory_sha}"
    )
    snapshot_id = uuid.uuid5(
        CATALOG_NAMESPACE,
        identity,
    )
    snapshot_prefix = (
        f"inventory/snapshots/{snapshot_id}"
        if resolved_scope == "default"
        else (
            f"inventory/scopes/{resolved_scope}/"
            f"snapshots/{snapshot_id}"
        )
    )
    snapshot = {
        "schema_version": 2,
        "snapshot_id": str(snapshot_id),
        "scope": resolved_scope,
        "source": "s3_inventory",
        "inventory_sha256": inventory_sha,
        "inventory_key": f"{snapshot_prefix}/inventory.jsonl",
        "manifest_key": f"{snapshot_prefix}/manifest.json",
        "document_count": len(documents),
        "artifact_count": sum(
            len(document["artifacts"]) for document in documents
        ),
        "collection_counts": dict(
            sorted(Counter(
                document["collection_slug"] for document in documents
            ).items())
        ),
        "collections": sorted(selected_slugs),
    }
    return snapshot, documents, uploads, inventory_payload


def _write_snapshot_files(
    snapshot: dict[str, Any],
    inventory_payload: bytes,
) -> Path:
    base_dir = settings.data_dir / "bootstrap" / "s3"
    output_dir = (
        base_dir / str(snapshot["snapshot_id"])
        if snapshot["scope"] == "default"
        else (
            base_dir
            / str(snapshot["scope"])
            / str(snapshot["snapshot_id"])
        )
    )
    inventory_path = output_dir / "inventory.jsonl"
    manifest_path = output_dir / "manifest.json"
    _atomic_bytes(inventory_path, inventory_payload)
    _atomic_bytes(
        manifest_path,
        (
            json.dumps(
                snapshot,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
    )
    print(
        f"Snapshot S3: {manifest_path} | "
        f"documentos={snapshot['document_count']} | "
        f"artefatos={snapshot['artifact_count']}"
    )
    return manifest_path


def plan_s3(
    *,
    inventory_path: str | Path | None = None,
    scope: str = "",
    collections: Iterable[str] | str | None = None,
    collection_path: str | Path | None = None,
) -> Path:
    snapshot, _, _, inventory_payload = _build_snapshot(
        inventory_path=inventory_path,
        scope=scope,
        collections=collections,
        collection_path=collection_path,
    )
    return _write_snapshot_files(snapshot, inventory_payload)


def _batches(values: list[Any], size: int) -> Iterable[list[Any]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _catalog_import(
    snapshot: dict[str, Any],
    documents: list[dict[str, Any]],
    *,
    batch_size: int,
) -> dict[str, Any]:
    base_url = os.getenv(
        "BASEIA_CATALOG_API_URL",
        "http://127.0.0.1:8088",
    ).rstrip("/")
    limits = httpx.Limits(
        max_connections=16,
        max_keepalive_connections=8,
        keepalive_expiry=30,
    )
    token = os.getenv("BASEIA_CATALOG_API_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else None
    with httpx.Client(
        base_url=base_url,
        limits=limits,
        timeout=120,
        headers=headers,
    ) as client:
        response = client.post(
            "/v1/inventory-snapshots",
            json={
                "id": snapshot["snapshot_id"],
                "scope": snapshot["scope"],
                "source": "s3_inventory",
                "manifest_key": snapshot["manifest_key"],
                "inventory_sha256": snapshot["inventory_sha256"],
                "expected_document_count": snapshot["document_count"],
                "expected_artifact_count": snapshot["artifact_count"],
            },
        )
        response.raise_for_status()
        catalog_snapshot = response.json()
        expected_identity = (
            str(snapshot["snapshot_id"]),
            str(snapshot["scope"]),
            int(snapshot["document_count"]),
            int(snapshot["artifact_count"]),
        )
        actual_identity = (
            str(catalog_snapshot.get("id")),
            str(catalog_snapshot.get("scope")),
            int(catalog_snapshot.get("expected_document_count", -1)),
            int(catalog_snapshot.get("expected_artifact_count", -1)),
        )
        if actual_identity != expected_identity:
            raise RuntimeError(
                "Catálogo retornou outro contrato de snapshot: "
                f"esperado={expected_identity}, atual={actual_identity}"
            )
        status = str(catalog_snapshot.get("status"))
        if status == "active":
            actual_counts = (
                int(catalog_snapshot.get("document_count", -1)),
                int(catalog_snapshot.get("artifact_count", -1)),
            )
            expected_counts = (
                int(snapshot["document_count"]),
                int(snapshot["artifact_count"]),
            )
            if actual_counts != expected_counts:
                raise RuntimeError(
                    "Snapshot ativo diverge das contagens locais: "
                    f"esperado={expected_counts}, atual={actual_counts}"
                )
            print(
                "Catálogo: snapshot já estava ativo e foi validado.",
                flush=True,
            )
            return {
                "status": "active",
                "reused": True,
                "document_count": actual_counts[0],
                "artifact_count": actual_counts[1],
            }
        if status != "loading":
            raise RuntimeError(
                "Snapshot existente não pode ser retomado: "
                f"status={status!r}"
            )
        imported = 0
        for batch in _batches(documents, batch_size):
            response = client.post(
                f"/v1/inventory-snapshots/{snapshot['snapshot_id']}/documents",
                json={"documents": batch},
            )
            response.raise_for_status()
            imported += len(batch)
            print(
                f"Catálogo: {imported}/{len(documents)} documentos",
                flush=True,
            )
        response = client.post(
            f"/v1/inventory-snapshots/{snapshot['snapshot_id']}/activate",
            json={
                "expected_document_count": snapshot["document_count"],
                "expected_artifact_count": snapshot["artifact_count"],
            },
        )
        response.raise_for_status()
        activated = response.json()
        if (
            str(activated.get("status")) != "active"
            or int(activated.get("document_count", -1))
            != int(snapshot["document_count"])
            or int(activated.get("artifact_count", -1))
            != int(snapshot["artifact_count"])
        ):
            raise RuntimeError(
                "Catálogo não confirmou a ativação e as contagens do snapshot."
            )
        return {
            "status": "active",
            "reused": False,
            "document_count": int(activated["document_count"]),
            "artifact_count": int(activated["artifact_count"]),
        }


def apply_s3(
    *,
    inventory_path: str | Path | None = None,
    scope: str = "",
    collections: Iterable[str] | str | None = None,
    collection_path: str | Path | None = None,
    batch_size: int = 100,
    upload_batch_size: int = 2000,
) -> dict[str, Any]:
    if batch_size < 1 or upload_batch_size < 1:
        raise ValueError("Tamanhos de lote devem ser positivos.")
    snapshot, documents, uploads, inventory_payload = _build_snapshot(
        inventory_path=inventory_path,
        scope=scope,
        collections=collections,
        collection_path=collection_path,
    )
    manifest_path = _write_snapshot_files(snapshot, inventory_payload)
    state_path = manifest_path.parent / "promotion-state.json"
    _atomic_bytes(
        state_path,
        (
            json.dumps(
                {
                    "snapshot_id": snapshot["snapshot_id"],
                    "scope": snapshot["scope"],
                    "status": "uploading",
                    "updated_at": _now(),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
    )
    store = S3ArtifactStore.from_env()
    try:
        store.ensure_bucket()
        verified = 0
        for batch in _batches(uploads, upload_batch_size):
            store.upload_many(batch, check_existing=True)
            verified += len(batch)
            print(
                f"S3: {verified}/{len(uploads)} objetos verificados",
                flush=True,
            )

        snapshot_dir = manifest_path.parent
        snapshot_uploads = [
            UploadRequest(
                source=snapshot_dir / "inventory.jsonl",
                key=str(snapshot["inventory_key"]),
                sha256=str(snapshot["inventory_sha256"]),
                content_type="application/x-ndjson",
            ),
            UploadRequest(
                source=manifest_path,
                key=str(snapshot["manifest_key"]),
                sha256=file_sha256(manifest_path),
                content_type="application/json",
            ),
        ]
        store.upload_many(snapshot_uploads, check_existing=True)

        if hashlib.sha256(inventory_payload).hexdigest() != str(
            snapshot["inventory_sha256"]
        ):
            raise RuntimeError("Inventory JSONL mudou durante a promoção.")

        catalog = _catalog_import(
            snapshot,
            documents,
            batch_size=batch_size,
        )
        report = {
            **snapshot,
            "bucket": store.bucket,
            "endpoint_url": store.endpoint_url,
            "verified_object_count": len(uploads) + len(snapshot_uploads),
            "catalog_activated": True,
            "catalog_reused": bool(catalog["reused"]),
            "completed_at": _now(),
        }
        report_path = manifest_path.parent / "promotion-report.json"
        _atomic_bytes(
            report_path,
            (
                json.dumps(
                    report,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8"),
        )
        _atomic_bytes(
            state_path,
            (
                json.dumps(
                    {
                        "snapshot_id": snapshot["snapshot_id"],
                        "scope": snapshot["scope"],
                        "status": "completed",
                        "catalog_reused": bool(catalog["reused"]),
                        "report_path": str(report_path.resolve()),
                        "updated_at": _now(),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8"),
        )
        return report
    except Exception as error:
        _atomic_bytes(
            state_path,
            (
                json.dumps(
                    {
                        "snapshot_id": snapshot["snapshot_id"],
                        "scope": snapshot["scope"],
                        "status": "failed",
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "updated_at": _now(),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8"),
        )
        raise
    finally:
        store.close()


def promote_s3(
    action: str = "plan",
    inventory: str = "",
    scope: str = "",
    collection: Iterable[str] | str | None = None,
    collection_path: str = "",
    batch_size: int = 100,
    upload_batch_size: int = 2000,
) -> Path | dict[str, Any]:
    if action == "plan":
        return plan_s3(
            inventory_path=inventory,
            scope=scope,
            collections=collection,
            collection_path=collection_path,
        )
    if action == "apply":
        return apply_s3(
            inventory_path=inventory,
            scope=scope,
            collections=collection,
            collection_path=collection_path,
            batch_size=batch_size,
            upload_batch_size=upload_batch_size,
        )
    raise ValueError("Ação inválida. Use plan ou apply.")
