"""Publish completed MinerU outputs directly to an S3-compatible store."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
from typing import Any

import boto3
import catalog_client
from boto3.s3.transfer import TransferConfig, create_transfer_manager
from botocore.config import Config
from botocore.exceptions import ClientError


def enabled() -> bool:
    return os.environ.get("MINERU_RESULT_STORE", "filesystem").casefold() == "s3"


def _settings() -> tuple[str, str, str]:
    endpoint = os.environ.get("BASEIA_S3_ENDPOINT_URL", "").strip().rstrip("/")
    bucket = os.environ.get("BASEIA_S3_BUCKET", "").strip()
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1").strip()
    if not endpoint or not bucket:
        raise RuntimeError(
            "Persistência S3 exige BASEIA_S3_ENDPOINT_URL e BASEIA_S3_BUCKET."
        )
    return endpoint, bucket, region


def _client() -> Any:
    endpoint, _, region = _settings()
    concurrency = max(
        1,
        int(os.environ.get("MINERU_S3_UPLOAD_CONCURRENCY", "8")),
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        config=Config(
            retries={"max_attempts": 8, "mode": "adaptive"},
            max_pool_connections=max(16, concurrency * 2),
            s3={"addressing_style": "path"},
        ),
    )


def ensure_bucket() -> None:
    client = _client()
    _, bucket, _ = _settings()
    try:
        try:
            client.head_bucket(Bucket=bucket)
            return
        except ClientError:
            if (
                os.environ.get("BASEIA_S3_CREATE_BUCKET", "false")
                .strip()
                .casefold()
                not in {"1", "true", "yes", "on"}
            ):
                raise
        client.create_bucket(Bucket=bucket)
        client.head_bucket(Bucket=bucket)
    finally:
        client.close()


def _normalize_key(value: str) -> str:
    raw = value.replace("\\", "/").strip("/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError(f"Chave S3 inválida: {value!r}")
    return path.as_posix()


def _head(client: Any, bucket: str, key: str) -> dict[str, Any] | None:
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        status = int(
            error.response.get("ResponseMetadata", {}).get(
                "HTTPStatusCode",
                0,
            )
        )
        if status == 404:
            return None
        raise


def _current(
    client: Any,
    bucket: str,
    *,
    key: str,
    sha256: str,
    size_bytes: int,
) -> bool:
    head = _head(client, bucket, key)
    if head is None:
        return False
    metadata = {
        str(name).casefold(): str(value)
        for name, value in head.get("Metadata", {}).items()
    }
    return (
        int(head.get("ContentLength", -1)) == size_bytes
        and metadata.get("sha256") == sha256
    )


def _kind(path: str) -> str:
    name = PurePosixPath(path).name
    suffix = PurePosixPath(path).suffix.casefold()
    if path.endswith("_middle.json"):
        return "mineru_middle_json"
    if path.endswith(("_content_list.json", "_content_list_v2.json")):
        return "mineru_content_list"
    if suffix == ".md":
        return "mineru_markdown"
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return "mineru_image"
    if suffix == ".pdf":
        return "mineru_pdf"
    if name == "service.json":
        return "mineru_service_manifest"
    return "mineru_artifact"


def _publish_with_client(
    client: Any,
    source: Path,
    task_manifest: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    _, bucket, _ = _settings()
    task_id = str(task_manifest["task_id"])
    document_prefix = str(task_manifest.get("artifact_prefix") or "").strip("/")
    prefix = _normalize_key(
        f"{document_prefix}/intermediate/mineru"
        if document_prefix
        else f"results/tasks/{task_id}"
    )
    manifest_key = _normalize_key(f"{prefix}/manifest.json")
    concurrency = max(
        1,
        int(os.environ.get("MINERU_S3_UPLOAD_CONCURRENCY", "8")),
    )
    prepared: list[dict[str, Any]] = []
    for artifact in artifacts:
        relative = _normalize_key(str(artifact["path"]))
        origin = source / Path(*PurePosixPath(relative).parts)
        if not origin.is_file():
            raise FileNotFoundError(origin)
        content_type = (
            mimetypes.guess_type(origin.name)[0]
            or "application/octet-stream"
        )
        prepared.append(
            {
                **artifact,
                "key": _normalize_key(f"{prefix}/{relative}"),
                "content_type": content_type,
                "kind": _kind(relative),
                "canonical": False,
                "origin_path": origin,
            }
        )

    # A commit manifest exists only after every artifact was verified. On the
    # normal first attempt there is therefore no reason to HEAD every key
    # before uploading it. Retries after a committed package retain the
    # per-object checks so they can repair only missing or stale objects.
    if _head(client, bucket, manifest_key) is None:
        pending = prepared
    else:
        pending = [
            artifact
            for artifact in prepared
            if not _current(
                client,
                bucket,
                key=str(artifact["key"]),
                sha256=str(artifact["sha256"]),
                size_bytes=int(artifact["bytes"]),
            )
        ]
    catalog_client.transition(
        str(task_manifest.get("stage_run_id") or "") or None,
        "uploading",
        lease_owner=str(task_manifest.get("lease_owner") or ""),
        lease_attempt=int(task_manifest.get("lease_attempt") or 0),
    )
    if pending:
        manager = create_transfer_manager(
            client,
            TransferConfig(
                multipart_threshold=16 * 1024 * 1024,
                multipart_chunksize=16 * 1024 * 1024,
                max_concurrency=concurrency,
            ),
        )
        try:
            futures = [
                manager.upload(
                    str(artifact["origin_path"]),
                    bucket,
                    str(artifact["key"]),
                    extra_args={
                        "ContentType": str(artifact["content_type"]),
                        "Metadata": {"sha256": str(artifact["sha256"])},
                    },
                )
                for artifact in pending
            ]
            for future in futures:
                future.result()
        finally:
            manager.shutdown()

    for artifact in prepared:
        if not _current(
            client,
            bucket,
            key=str(artifact["key"]),
            sha256=str(artifact["sha256"]),
            size_bytes=int(artifact["bytes"]),
        ):
            raise RuntimeError(
                f"S3 não confirmou o artefato {artifact['key']}."
            )

    persisted_at = str(
        task_manifest.get("persisted_at")
        or task_manifest.get("completed_at")
        or ""
    )
    if not persisted_at:
        raise RuntimeError(
            "Task concluída sem completed_at determinístico."
        )
    public_artifacts = [
        {
            key: value
            for key, value in artifact.items()
            if key != "origin_path"
        }
        for artifact in prepared
    ]
    package_manifest = {
        "schema_version": 2,
        "task_id": task_id,
        "idempotency_key": task_manifest.get("idempotency_key"),
        "correlation_key": task_manifest.get("correlation_key"),
        "document_revision_id": task_manifest.get("document_revision_id"),
        "stage_run_id": task_manifest.get("stage_run_id"),
        "stage": task_manifest.get("stage") or "extract",
        "processor": task_manifest.get("processor") or "mineru",
        "processor_version": task_manifest.get("processor_version"),
        "config_hash": task_manifest.get("config_hash"),
        "status": "completed",
        "created_at": task_manifest.get("created_at"),
        "started_at": task_manifest.get("started_at"),
        "completed_at": task_manifest.get("completed_at"),
        "persisted_at": persisted_at,
        "page_count": task_manifest.get("page_count"),
        "duration_seconds": task_manifest.get("duration_seconds"),
        "file_count": len(public_artifacts),
        "artifact_bytes": sum(
            int(item["bytes"]) for item in public_artifacts
        ),
        "artifacts": public_artifacts,
        "result_ref": {
            "scheme": "s3",
            "bucket": bucket,
            "prefix": prefix,
            "manifest_key": manifest_key,
        },
    }
    manifest_payload = (
        json.dumps(
            package_manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
    client.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=manifest_payload,
        ContentType="application/json",
        Metadata={"sha256": manifest_sha256},
    )
    if not _current(
        client,
        bucket,
        key=manifest_key,
        sha256=manifest_sha256,
        size_bytes=len(manifest_payload),
    ):
        raise RuntimeError(f"S3 não confirmou o commit manifest {manifest_key}.")

    catalog_client.transition(
        str(task_manifest.get("stage_run_id") or "") or None,
        "cataloging",
        lease_owner=str(task_manifest.get("lease_owner") or ""),
        lease_attempt=int(task_manifest.get("lease_attempt") or 0),
    )
    catalog_artifacts = [
        {
            "kind": str(artifact["kind"]),
            "object_key": str(artifact["key"]),
            "checksum_sha256": str(artifact["sha256"]),
            "size_bytes": int(artifact["bytes"]),
            "content_type": str(artifact["content_type"]),
            "canonical": False,
        }
        for artifact in public_artifacts
    ]
    catalog_artifacts.append(
        {
            "kind": "mineru_result_manifest",
            "object_key": manifest_key,
            "checksum_sha256": manifest_sha256,
            "size_bytes": len(manifest_payload),
            "content_type": "application/json",
            "canonical": False,
        }
    )
    catalog_client.complete(
        str(task_manifest.get("stage_run_id") or "") or None,
        catalog_artifacts,
        lease_owner=str(task_manifest.get("lease_owner") or ""),
        lease_attempt=int(task_manifest.get("lease_attempt") or 0),
    )
    return package_manifest


def publish(
    source: Path,
    task_manifest: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Upload every artifact and publish ``manifest.json`` last.

    The commit manifest is the visibility boundary. Catalog completion occurs
    only after every object was confirmed by size and SHA-256 metadata. The
    payload is deterministic across retries of the same completed task.
    """

    client = _client()
    try:
        return _publish_with_client(
            client,
            source,
            task_manifest,
            artifacts,
        )
    finally:
        client.close()
