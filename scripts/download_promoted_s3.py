from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import boto3
from botocore.config import Config
from tenacity import Retrying, stop_after_attempt, wait_exponential

from baseia_extract.mineru import ManifestStore
from baseia_extract.schemas import ExtractionManifest
from baseia_extract.settings import settings


@dataclass(frozen=True, slots=True)
class ArtifactDownload:
    document_sha256: str
    task_id: str
    key: str
    destination: Path
    expected_bytes: int
    expected_sha256: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materializa localmente os pacotes completos dos resultados "
            "canônicos promovidos do S3."
        )
    )
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--endpoint-url", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--downloads", type=int, default=24)
    return parser.parse_args()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".dl-{uuid.uuid4().hex[:12]}.part"
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _promoted_manifests() -> list[ExtractionManifest]:
    root = settings.mineru_output_dir / "manifests"
    promoted: list[ExtractionManifest] = []
    for path in root.rglob("*.json"):
        manifest = ExtractionManifest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        canonical = manifest.controller.get("canonical_source", {})
        if canonical.get("kind") == "s3_promotion":
            promoted.append(manifest)
    return sorted(promoted, key=lambda item: item.sha256)


def _safe_relative_path(value: str) -> Path:
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise ValueError(f"Caminho de artefato inseguro: {value!r}")
    if ":" in relative.parts[0]:
        raise ValueError(f"Caminho de artefato inseguro: {value!r}")
    return Path(*relative.parts)


def _get_bytes(client: Any, bucket: str, key: str) -> bytes:
    for attempt in Retrying(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        reraise=True,
    ):
        with attempt:
            response = client.get_object(Bucket=bucket, Key=key)
            body = response["Body"]
            try:
                return body.read()
            finally:
                body.close()
    raise RuntimeError(f"Retry encerrado sem baixar {key}.")


def _normalized_artifacts(
    artifacts: list[dict[str, Any]],
) -> list[tuple[str, int, str]]:
    return sorted(
        (
            str(item["path"]),
            int(item["bytes"]),
            str(item["sha256"]).lower(),
        )
        for item in artifacts
    )


def _load_remote_package(
    client: Any,
    bucket: str,
    manifest: ExtractionManifest,
) -> tuple[bytes, list[dict[str, Any]]]:
    if not manifest.task_id:
        raise ValueError(f"{manifest.sha256}: manifesto sem task_id.")
    key = f"results/tasks/{manifest.task_id}/manifest.json"
    payload = _get_bytes(client, bucket, key)
    remote = json.loads(payload)
    if remote.get("status") != "completed":
        raise ValueError(
            f"{manifest.sha256}: task remota não está concluída."
        )
    if str(remote.get("task_id")) != manifest.task_id:
        raise ValueError(f"{manifest.sha256}: task_id remoto divergente.")
    if str(remote.get("correlation_key")).lower() != manifest.sha256:
        raise ValueError(
            f"{manifest.sha256}: correlation_key remoto divergente."
        )
    artifacts = remote.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError(f"{manifest.sha256}: pacote remoto sem artefatos.")
    if _normalized_artifacts(artifacts) != _normalized_artifacts(
        manifest.artifacts
    ):
        raise ValueError(
            f"{manifest.sha256}: artefatos remotos divergiram do canônico."
        )
    return payload, artifacts


def _safe_load_remote_package(
    client: Any,
    bucket: str,
    manifest: ExtractionManifest,
) -> tuple[
    ExtractionManifest,
    bytes | None,
    list[dict[str, Any]] | None,
    str | None,
]:
    try:
        payload, artifacts = _load_remote_package(client, bucket, manifest)
        return manifest, payload, artifacts, None
    except Exception as error:
        return (
            manifest,
            None,
            None,
            f"{type(error).__name__}: {error}",
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _already_valid(target: ArtifactDownload) -> bool:
    return (
        target.destination.is_file()
        and target.destination.stat().st_size == target.expected_bytes
        and _file_sha256(target.destination) == target.expected_sha256
    )


def _download_artifact(
    client: Any,
    bucket: str,
    target: ArtifactDownload,
) -> tuple[str, str, str | None]:
    if _already_valid(target):
        return target.document_sha256, "reused", None

    target.destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in Retrying(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        reraise=True,
    ):
        with attempt:
            temporary = (
                target.destination.parent
                / f".dl-{uuid.uuid4().hex[:12]}.part"
            )
            try:
                response = client.get_object(Bucket=bucket, Key=target.key)
                body = response["Body"]
                digest = hashlib.sha256()
                size = 0
                try:
                    with temporary.open("wb") as destination:
                        while chunk := body.read(1024 * 1024):
                            destination.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                finally:
                    body.close()
                if size != target.expected_bytes:
                    raise ValueError(
                        f"{target.key}: tamanho {size}, esperado "
                        f"{target.expected_bytes}."
                    )
                actual_sha256 = digest.hexdigest()
                if actual_sha256 != target.expected_sha256:
                    raise ValueError(
                        f"{target.key}: SHA-256 {actual_sha256}, esperado "
                        f"{target.expected_sha256}."
                    )
                os.replace(temporary, target.destination)
                return target.document_sha256, "downloaded", None
            finally:
                temporary.unlink(missing_ok=True)
    raise RuntimeError(f"Retry encerrado sem baixar {target.key}.")


def _safe_download(
    client: Any,
    bucket: str,
    target: ArtifactDownload,
) -> tuple[str, str, str | None]:
    try:
        return _download_artifact(client, bucket, target)
    except Exception as error:
        return (
            target.document_sha256,
            "error",
            f"{type(error).__name__}: {error}",
        )


def main() -> int:
    args = _parse_args()
    if args.downloads < 1:
        raise ValueError("downloads deve ser positivo.")

    client = boto3.client(
        "s3",
        endpoint_url=args.endpoint_url,
        region_name=args.region,
        config=Config(
            retries={"max_attempts": 8, "mode": "adaptive"},
            max_pool_connections=max(16, args.downloads * 2),
        ),
    )
    manifests = _promoted_manifests()
    if not manifests:
        raise RuntimeError("Nenhum manifesto promovido do S3 foi encontrado.")

    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    report_root = (
        settings.mineru_output_dir / "s3-downloads" / run_id
    )
    records_root = settings.mineru_output_dir / "s3-downloads" / "records"
    report_root.mkdir(parents=True, exist_ok=True)

    targets: list[ArtifactDownload] = []
    remote_manifest_sha256: dict[str, str] = {}
    package_errors: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=args.downloads) as executor:
        futures = [
            executor.submit(
                _safe_load_remote_package,
                client,
                args.bucket,
                manifest,
            )
            for manifest in manifests
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            package = future.result()
            manifest, payload, artifacts, error = package
            if error is not None or payload is None or artifacts is None:
                package_errors.setdefault(manifest.sha256, []).append(
                    error or "Falha desconhecida ao carregar manifesto remoto."
                )
            else:
                task_manifest_path = manifest.output_dir / "manifest.json"
                _atomic_bytes(task_manifest_path, payload)
                remote_manifest_sha256[manifest.sha256] = hashlib.sha256(
                    payload
                ).hexdigest()
                prefix = f"results/tasks/{manifest.task_id}/"
                for artifact in artifacts:
                    relative = _safe_relative_path(str(artifact["path"]))
                    targets.append(
                        ArtifactDownload(
                            document_sha256=manifest.sha256,
                            task_id=str(manifest.task_id),
                            key=f"{prefix}{artifact['path']}",
                            destination=manifest.output_dir / relative,
                            expected_bytes=int(artifact["bytes"]),
                            expected_sha256=str(artifact["sha256"]).lower(),
                        )
                    )
            if index % 100 == 0 or index == len(manifests):
                print(
                    f"Manifestos remotos: {index}/{len(manifests)}",
                    flush=True,
                )

    downloaded = 0
    reused = 0
    with ThreadPoolExecutor(max_workers=args.downloads) as executor:
        results = executor.map(
            lambda target: _safe_download(client, args.bucket, target),
            targets,
        )
        for index, (sha256, status, error) in enumerate(results, start=1):
            if status == "downloaded":
                downloaded += 1
            elif status == "reused":
                reused += 1
            else:
                package_errors.setdefault(sha256, []).append(
                    error or "Erro desconhecido."
                )
            if index % 512 == 0 or index == len(targets):
                print(
                    f"Artefatos: {index}/{len(targets)} "
                    f"(baixados={downloaded}, reutilizados={reused}, "
                    f"erros={sum(map(len, package_errors.values()))})",
                    flush=True,
                )

    materialized_at = datetime.now(timezone.utc).isoformat()
    store = ManifestStore(settings.mineru_output_dir / "manifests")
    completed = 0
    for manifest in manifests:
        errors = package_errors.get(manifest.sha256, [])
        record = {
            "sha256": manifest.sha256,
            "document_id": manifest.document_id,
            "task_id": manifest.task_id,
            "bucket": args.bucket,
            "artifact_uri": manifest.artifact_uri,
            "output_dir": str(manifest.output_dir.resolve()),
            "artifact_count": len(manifest.artifacts),
            "artifact_bytes": sum(
                int(item["bytes"]) for item in manifest.artifacts
            ),
            "task_manifest_sha256": remote_manifest_sha256.get(
                manifest.sha256
            ),
            "materialized_at": materialized_at if not errors else None,
            "errors": errors,
        }
        if not errors:
            controller = dict(manifest.controller)
            controller["local_materialization"] = {
                "kind": "complete_s3_task_package",
                "path": str(manifest.output_dir.resolve()),
                "materialized_at": materialized_at,
                "validation": "declared-size-and-sha256",
                "task_manifest_sha256": remote_manifest_sha256[
                    manifest.sha256
                ],
            }
            history = list(manifest.task_history)
            if not any(
                isinstance(item, dict)
                and item.get("event") == "s3_package_materialized"
                and item.get("task_id") == manifest.task_id
                for item in history
            ):
                history.append(
                    {
                        "event": "s3_package_materialized",
                        "task_id": manifest.task_id,
                        "at": materialized_at,
                        "path": str(manifest.output_dir.resolve()),
                    }
                )
            store.save(
                manifest.model_copy(
                    update={
                        "controller": controller,
                        "task_history": history,
                        "updated_at": materialized_at,
                    }
                )
            )
            completed += 1
        _atomic_json(
            records_root / f"{manifest.sha256}.json",
            record,
        )

    finished_at = datetime.now(timezone.utc)
    report = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "bucket": args.bucket,
        "endpoint_url": args.endpoint_url,
        "region": args.region,
        "manifest_count": len(manifests),
        "materialized_count": completed,
        "failed_document_count": len(package_errors),
        "artifact_count": len(targets),
        "downloaded_artifact_count": downloaded,
        "reused_artifact_count": reused,
        "artifact_bytes": sum(item.expected_bytes for item in targets),
        "errors": package_errors,
    }
    _atomic_json(report_root / "report.json", report)
    _atomic_json(
        settings.mineru_output_dir / "s3-downloads" / "current.json",
        {
            "run_id": run_id,
            "report_path": str((report_root / "report.json").resolve()),
            "materialized_count": completed,
            "failed_document_count": len(package_errors),
        },
    )
    print(
        f"Materializados {completed}/{len(manifests)} pacotes; "
        f"artefatos baixados={downloaded}, reutilizados={reused}, "
        f"documentos com erro={len(package_errors)}.",
        flush=True,
    )
    return 1 if package_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
