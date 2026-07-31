from __future__ import annotations

import json
import mimetypes
import os
import socket
import tempfile
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event, Thread
from typing import Any, Self

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .document_manifest import (
    document_storage_keys,
    serialize_document_manifest,
    write_document_manifest_payload,
)
from .identity import canonical_json_sha256, stage_idempotency_key
from .layout import document_layout
from .storage import S3ArtifactStore, UploadRequest, file_sha256

_PUBLISHER_ID = (
    f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}"
)
_CANONICAL_KINDS = {
    "canonical_document_ir",
    "canonical_structure",
    "canonical_document_metadata",
    "canonical_markdown",
    "canonical_render_manifest",
}
_CANONICAL_FILES = (
    (
        "canonical_document_ir",
        "canonical/document_ir.json",
        "ir_path",
    ),
    (
        "canonical_structure",
        "canonical/structure.json",
        "structure_path",
    ),
    (
        "canonical_document_metadata",
        "canonical/metadata.json",
        "metadata_path",
    ),
    (
        "canonical_markdown",
        "canonical/document.md",
        "markdown_path",
    ),
    (
        "canonical_render_manifest",
        "canonical/render.json",
        "render_path",
    ),
)


class CatalogUnavailable(RuntimeError):
    pass


class RenderPublicationError(RuntimeError):
    pass


class _CatalogClient:
    def __init__(self, *, max_connections: int) -> None:
        base_url = os.getenv("BASEIA_CATALOG_API_URL", "").strip().rstrip("/")
        if not base_url:
            raise ValueError(
                "BASEIA_RENDER_PUBLISH_S3 exige BASEIA_CATALOG_API_URL."
            )
        token = os.getenv("BASEIA_CATALOG_API_TOKEN", "").strip()
        self._client = httpx.Client(
            base_url=base_url,
            headers=(
                {"Authorization": f"Bearer {token}"}
                if token
                else None
            ),
            timeout=60,
            limits=httpx.Limits(
                max_connections=max(4, max_connections),
                max_keepalive_connections=max(4, max_connections),
                keepalive_expiry=30,
            ),
        )

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
        *,
        attempts: int = 5,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        for attempt in Retrying(
            retry=retry_if_exception_type(CatalogUnavailable),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            stop=stop_after_attempt(attempts),
            reraise=True,
        ):
            with attempt:
                try:
                    request_kwargs: dict[str, Any] = {"json": payload}
                    if timeout is not None:
                        request_kwargs["timeout"] = timeout
                    response = self._client.request(
                        method,
                        path,
                        **request_kwargs,
                    )
                except (
                    httpx.TimeoutException,
                    httpx.NetworkError,
                ) as error:
                    raise CatalogUnavailable(
                        f"Catálogo indisponível: {type(error).__name__}: "
                        f"{error}"
                    ) from error
                if response.status_code >= 500:
                    raise CatalogUnavailable(
                        f"Catálogo respondeu HTTP {response.status_code}: "
                        f"{response.text[:1000]}"
                    )
                try:
                    response.raise_for_status()
                    value = response.json()
                except (httpx.HTTPStatusError, ValueError) as error:
                    raise RenderPublicationError(
                        f"Catálogo rejeitou {method} {path}: "
                        f"HTTP {response.status_code}: "
                        f"{response.text[:1000]}"
                    ) from error
                if not isinstance(value, dict):
                    raise RenderPublicationError(
                        f"Catálogo retornou JSON inválido para {path}."
                    )
                return value
        raise AssertionError("Retry do catálogo terminou inesperadamente.")


class _LeaseHeartbeat:
    def __init__(
        self,
        *,
        client: _CatalogClient,
        run_id: str,
        lease: dict[str, Any],
        lease_seconds: int,
    ) -> None:
        self._client = client
        self._run_id = run_id
        self._lease = lease
        self._interval = max(15.0, min(60.0, lease_seconds / 3))
        self._stop = Event()
        self._error: BaseException | None = None
        self._thread = Thread(
            target=self._run,
            name=f"render-heartbeat-{run_id[:8]}",
            daemon=True,
        )

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._client.request(
                    "POST",
                    f"/v1/stage-runs/{self._run_id}/heartbeat",
                    self._lease,
                    attempts=3,
                    timeout=10,
                )
            except BaseException as error:  # noqa: BLE001
                self._error = error
                return

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self._stop.set()
        self._thread.join(timeout=35)
        if self._thread.is_alive() and exc_type is None:
            raise RenderPublicationError(
                f"Heartbeat do stage {self._run_id} não encerrou."
            )
        if self._error is not None and exc_type is None:
            raise RenderPublicationError(
                f"Heartbeat do stage {self._run_id} falhou: "
                f"{type(self._error).__name__}: {self._error}"
            ) from self._error


def _catalog_artifact(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": str(record["kind"]),
        "object_key": str(record["object_key"]),
        "checksum_sha256": str(record["sha256"]),
        "size_bytes": int(record["bytes"]),
        "content_type": str(record["content_type"]),
        "canonical": bool(record["canonical"]),
    }


def _orphan_best_effort(
    client: _CatalogClient,
    *,
    run_id: str,
    lease: dict[str, Any],
) -> None:
    try:
        client.request(
            "POST",
            f"/v1/stage-runs/{run_id}/status",
            {"status": "orphaned", **lease},
            attempts=1,
            timeout=10,
        )
    except Exception:  # noqa: BLE001,S110
        # O erro original é o diagnóstico relevante. Se o catálogo também
        # estiver indisponível, o lease expirará normalmente.
        pass


def _load_local_manifest(row: dict[str, Any]) -> dict[str, Any]:
    layout = document_layout(row)
    try:
        value = json.loads(
            layout.manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise RenderPublicationError(
            f"Manifest local inválido: {layout.manifest_path}"
        ) from error
    if not isinstance(value, dict) or value.get("schema_version") != 2:
        raise RenderPublicationError(
            f"Manifest local não usa schema_version=2: "
            f"{layout.manifest_path}"
        )
    expected = {
        "document_id": str(row["document_id"]),
        "revision_id": str(row["revision_id"]),
        "sha256": str(row["sha256"]).casefold(),
    }
    for field, declared in expected.items():
        if str(value.get(field) or "").casefold() != declared.casefold():
            raise RenderPublicationError(
                f"Manifest local diverge em {field}: "
                f"{layout.manifest_path}"
            )
    return value


def _canonical_records(
    row: dict[str, Any],
    *,
    stage_run_id: str,
) -> list[dict[str, Any]]:
    layout = document_layout(row)
    _, artifact_prefix = document_storage_keys(row)
    records: list[dict[str, Any]] = []
    for kind, relative, attribute in _CANONICAL_FILES:
        path = Path(getattr(layout, attribute))
        if not path.is_file():
            raise FileNotFoundError(path)
        records.append(
            {
                "kind": kind,
                "local_path": str(path),
                "object_key": f"{artifact_prefix}/{relative}",
                "sha256": file_sha256(path),
                "bytes": path.stat().st_size,
                "content_type": (
                    mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream"
                ),
                "canonical": True,
                "origin": "stage",
                "stage_run_id": stage_run_id,
            }
        )
    return records


def _manifest_payload(
    row: dict[str, Any],
    *,
    existing: dict[str, Any],
    canonical: list[dict[str, Any]],
    stage_run_id: str,
    idempotency_key: str,
    config_hash: str,
    middle_sha256: str,
    renderer_version: int,
) -> dict[str, Any]:
    replacements = {
        str(record["object_key"]): {
            key: value
            for key, value in record.items()
            if key != "local_path"
        }
        for record in canonical
    }
    seen: set[str] = set()
    artifacts: list[dict[str, Any]] = []
    for value in existing.get("artifacts", []):
        if not isinstance(value, dict) or not value.get("object_key"):
            raise RenderPublicationError(
                f"Artifact inválido no manifest de {row['document_id']}."
            )
        key = str(value["object_key"])
        if key in seen:
            raise RenderPublicationError(
                f"Artifact duplicado no manifest: {key}"
            )
        seen.add(key)
        artifacts.append(dict(replacements.get(key, value)))
    for key in sorted(replacements.keys() - seen):
        artifacts.append(replacements[key])

    stage_state = {
        "stage": "render",
        "stage_run_id": stage_run_id,
        "idempotency_key": idempotency_key,
        "processor": "baseia-render",
        "processor_version": str(renderer_version),
        "config_hash": config_hash,
        "input_hashes": [middle_sha256],
    }
    existing_stages = existing.get("stage_runs")
    stages = [
        dict(value)
        for value in (
            existing_stages if isinstance(existing_stages, list) else []
        )
        if isinstance(value, dict)
        and not (
            value.get("stage") == "render"
            and (
                value.get("stage_run_id") == stage_run_id
                or value.get("idempotency_key") == idempotency_key
            )
        )
    ]
    stages.append(stage_state)
    return {
        **existing,
        "origin": "stage",
        "artifacts": artifacts,
        "stage_runs": stages,
    }


def _temporary_manifest(
    row: dict[str, Any],
    payload: dict[str, Any],
) -> Path:
    layout = document_layout(row)
    descriptor, name = tempfile.mkstemp(
        prefix=".manifest.render-publish.",
        suffix=".tmp",
        dir=layout.document_dir,
    )
    path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(serialize_document_manifest(payload))
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def _restore_completed_manifest(
    row: dict[str, Any],
    *,
    run: dict[str, Any],
    store: S3ArtifactStore,
) -> None:
    expected = next(
        (
            artifact
            for artifact in run.get("artifacts", [])
            if isinstance(artifact, dict)
            and artifact.get("kind") == "document_manifest"
        ),
        None,
    )
    if expected is None:
        raise RenderPublicationError(
            f"Stage concluído {run['id']} sem document_manifest."
        )
    layout = document_layout(row)
    expected_sha = str(expected["checksum_sha256"])
    if (
        layout.manifest_path.is_file()
        and file_sha256(layout.manifest_path) == expected_sha
    ):
        return
    temporary = layout.document_dir / (
        f".manifest.{run['id']}.restore.tmp"
    )
    try:
        store.download_file(
            str(expected["object_key"]),
            temporary,
            expected_sha256=expected_sha,
        )
        payload = json.loads(temporary.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RenderPublicationError(
                f"Manifest S3 inválido do stage {run['id']}."
            )
        if str(payload.get("sha256") or "").casefold() != str(
            row["sha256"]
        ).casefold():
            raise RenderPublicationError(
                f"Manifest S3 pertence a outra revisão no stage {run['id']}."
            )
        write_document_manifest_payload(row, payload)
        if file_sha256(layout.manifest_path) != expected_sha:
            raise RenderPublicationError(
                f"Manifest local não reproduziu o stage {run['id']}."
            )
    finally:
        temporary.unlink(missing_ok=True)


def _publish_one(
    row: dict[str, Any],
    *,
    client: _CatalogClient,
    store: S3ArtifactStore,
    render_source: str,
    renderer_version: int,
    lease_seconds: int,
    lease_owner: str,
) -> dict[str, Any]:
    layout = document_layout(row)
    render_metadata = json.loads(
        layout.render_path.read_text(encoding="utf-8")
    )
    middle_sha256 = str(render_metadata.get("middle_sha256") or "")
    config_hash = canonical_json_sha256(
        {
            "render_source": render_source,
            "renderer_version": renderer_version,
        }
    )
    idempotency_key = stage_idempotency_key(
        revision_id=str(row["revision_id"]),
        stage="render",
        processor="baseia-render",
        processor_version=str(renderer_version),
        config_hash=config_hash,
        input_hashes=[middle_sha256],
    )
    run = client.request(
        "POST",
        "/v1/stage-runs/get-or-create",
        {
            "document_revision_id": str(row["revision_id"]),
            "stage": "render",
            "processor": "baseia-render",
            "processor_version": str(renderer_version),
            "config_hash": config_hash,
            "input_hashes": [middle_sha256],
            "idempotency_key": idempotency_key,
            "lease_owner": lease_owner,
            "lease_seconds": lease_seconds,
        },
    )
    if str(run.get("status")) == "completed":
        _restore_completed_manifest(row, run=run, store=store)
        return {
            "document_id": str(row["document_id"]),
            "status": "completed",
            "stage_run_id": str(run["id"]),
            "reused": True,
        }
    if str(run.get("status")) in {"failed", "cancelled"}:
        return {
            "document_id": str(row["document_id"]),
            "status": "error",
            "stage_run_id": str(run["id"]),
            "reason": (
                f"stage render terminal em {run['status']}: "
                f"{run.get('error') or 'sem detalhe'}"
            ),
        }
    if not bool(run.get("claimed")):
        return {
            "document_id": str(row["document_id"]),
            "status": "pending",
            "stage_run_id": str(run["id"]),
            "reason": "stage render já possui outro lease ativo",
        }

    run_id = str(run["id"])
    lease_attempt = int(run["attempt"])
    lease = {
        "lease_owner": lease_owner,
        "lease_attempt": lease_attempt,
        "lease_seconds": lease_seconds,
    }
    client.request(
        "POST",
        f"/v1/stage-runs/{run_id}/status",
        {"status": "processing", **lease},
    )

    try:
        existing_manifest = _load_local_manifest(row)
        canonical = _canonical_records(
            row,
            stage_run_id=run_id,
        )
        if {
            str(record["kind"]) for record in canonical
        } != _CANONICAL_KINDS:
            raise RenderPublicationError(
                f"Conjunto canônico incompleto para {row['document_id']}."
            )
        canonical_keys = {
            str(record["object_key"]) for record in canonical
        }
        payload = _manifest_payload(
            row,
            existing=existing_manifest,
            canonical=canonical,
            stage_run_id=run_id,
            idempotency_key=idempotency_key,
            config_hash=config_hash,
            middle_sha256=middle_sha256,
            renderer_version=renderer_version,
        )
        _, artifact_prefix = document_storage_keys(row)
        manifest_key = f"{artifact_prefix}/manifest.json"
        if len(canonical_keys) != len(_CANONICAL_KINDS):
            raise RenderPublicationError(
                f"Chaves canônicas colidiram para {row['document_id']}."
            )
        temporary_manifest = _temporary_manifest(row, payload)
        manifest_record = {
            "kind": "document_manifest",
            "object_key": manifest_key,
            "sha256": file_sha256(temporary_manifest),
            "bytes": temporary_manifest.stat().st_size,
            "content_type": "application/json",
            "canonical": True,
        }
    except Exception:
        _orphan_best_effort(client, run_id=run_id, lease=lease)
        raise

    try:
        client.request(
            "POST",
            f"/v1/stage-runs/{run_id}/status",
            {"status": "uploading", **lease},
        )
        with _LeaseHeartbeat(
            client=client,
            run_id=run_id,
            lease=lease,
            lease_seconds=lease_seconds,
        ):
            store.upload_many(
                [
                    UploadRequest(
                        source=Path(str(record["local_path"])),
                        key=str(record["object_key"]),
                        sha256=str(record["sha256"]),
                        content_type=str(record["content_type"]),
                    )
                    for record in canonical
                ]
            )
            # O manifest é o commit marker do conjunto e sempre vai por último.
            store.upload_file(
                temporary_manifest,
                manifest_key,
                sha256=str(manifest_record["sha256"]),
                content_type="application/json",
            )
        client.request(
            "POST",
            f"/v1/stage-runs/{run_id}/status",
            {"status": "cataloging", **lease},
        )
        completed = client.request(
            "POST",
            f"/v1/stage-runs/{run_id}/complete",
            {
                "artifacts": [
                    *(_catalog_artifact(record) for record in canonical),
                    _catalog_artifact(manifest_record),
                ],
                "lease_owner": lease_owner,
                "lease_attempt": lease_attempt,
            },
        )
        if str(completed.get("status")) != "completed":
            raise RenderPublicationError(
                f"Catálogo não concluiu o render {run_id}."
            )
        write_document_manifest_payload(row, payload)
        if file_sha256(layout.manifest_path) != manifest_record["sha256"]:
            raise RenderPublicationError(
                f"Manifest local divergiu do S3 no stage {run_id}."
            )
    except Exception:
        _orphan_best_effort(client, run_id=run_id, lease=lease)
        raise
    finally:
        temporary_manifest.unlink(missing_ok=True)
    return {
        "document_id": str(row["document_id"]),
        "status": "completed",
        "stage_run_id": run_id,
        "artifact_count": len(canonical) + 1,
        "manifest_key": manifest_key,
        "reused": False,
    }


def publish_render_outputs(
    rows: list[dict[str, Any]],
    *,
    render_source: str,
    renderer_version: int,
    concurrency: int,
    transfer_concurrency: int,
) -> dict[str, Any]:
    if concurrency < 1 or transfer_concurrency < 1:
        raise ValueError("Concorrências de publicação devem ser positivas.")
    if not rows:
        return {"counts": {}, "documents": []}
    lease_seconds = int(os.getenv("BASEIA_STAGE_LEASE_SECONDS", "7200"))
    if not 60 <= lease_seconds <= 86400:
        raise ValueError(
            "BASEIA_STAGE_LEASE_SECONDS deve ficar entre 60 e 86400."
        )
    client = _CatalogClient(max_connections=concurrency * 2)
    store: S3ArtifactStore | None = None
    results: list[dict[str, Any] | None] = [None] * len(rows)
    try:
        store = S3ArtifactStore.from_env(
            max_concurrency=transfer_concurrency
        )
        store.ensure_bucket()
        with ThreadPoolExecutor(
            max_workers=concurrency,
            thread_name_prefix="render-publish",
        ) as executor:
            futures = {
                executor.submit(
                    _publish_one,
                    row,
                    client=client,
                    store=store,
                    render_source=render_source,
                    renderer_version=renderer_version,
                    lease_seconds=lease_seconds,
                    lease_owner=(
                        f"{_PUBLISHER_ID}:{uuid.uuid4().hex[:8]}:{index}"
                    ),
                ): index
                for index, row in enumerate(rows)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    results[index] = future.result()
                except Exception as error:  # noqa: BLE001
                    results[index] = {
                        "document_id": str(rows[index]["document_id"]),
                        "status": "error",
                        "reason": f"{type(error).__name__}: {error}",
                    }
    finally:
        if store is not None:
            store.close()
        client.close()
    completed = [item for item in results if item is not None]
    return {
        "counts": dict(
            sorted(Counter(item["status"] for item in completed).items())
        ),
        "documents": completed,
    }
