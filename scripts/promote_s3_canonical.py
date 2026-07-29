from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from s3transfer.manager import TransferConfig, TransferManager

from baseia_extract.mineru import (
    ManifestStore,
    WorkItem,
    _load_manifest,
    _reconcile_manifests,
    _write_reconciliation_summary,
)
from baseia_extract.schemas import DocumentRecord, ExtractionManifest
from baseia_extract.settings import settings


TASK_ID_PATTERN = re.compile(
    r"^(?:[0-9a-f]{64}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class S3Candidate:
    sha256: str
    task_id: str
    index_key: str
    last_modified: datetime


@dataclass(frozen=True, slots=True)
class Artifact:
    sha256: str
    task_id: str
    path: str
    expected_bytes: int
    expected_sha256: str

    @property
    def key(self) -> str:
        return f"results/tasks/{self.task_id}/{self.path}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Promove resultados S3 recentes e íntegros para os manifestos "
            "canônicos sem usar o S3 como fonte primária."
        )
    )
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--endpoint-url", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument(
        "--pod-task-list",
        action="append",
        type=Path,
        required=True,
        help="Arquivo com um SHA/task_id por linha, obtido do Volume Disk.",
    )
    parser.add_argument(
        "--since",
        type=datetime.fromisoformat,
        required=True,
        help="Início UTC da janela promovível, em ISO-8601.",
    )
    parser.add_argument(
        "--previous-audit",
        type=Path,
        help="JSONL anterior com tarefas já validadas por SHA-256.",
    )
    parser.add_argument("--downloads", type=int, default=24)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_pod_tasks(paths: list[Path]) -> set[str]:
    tasks: set[str] = set()
    for path in paths:
        for value in path.read_text(encoding="utf-8").splitlines():
            normalized = value.strip().lower()
            if len(normalized) == 64:
                bytes.fromhex(normalized)
                tasks.add(normalized)
    return tasks


def _latest_s3_candidates(client: Any, bucket: str) -> dict[str, S3Candidate]:
    latest: dict[str, S3Candidate] = {}
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="results/by-sha/"):
        for item in page.get("Contents", []):
            key = str(item["Key"])
            parts = key.split("/")
            if len(parts) < 5:
                continue
            sha256 = parts[3].lower()
            try:
                bytes.fromhex(sha256)
            except ValueError:
                continue
            if len(sha256) != 64:
                continue
            filename = parts[4]
            if not filename.casefold().endswith(".json"):
                continue
            task_id = filename[:-5]
            if TASK_ID_PATTERN.fullmatch(task_id) is None:
                continue
            candidate = S3Candidate(
                sha256=sha256,
                task_id=task_id,
                index_key=key,
                last_modified=item["LastModified"],
            )
            current = latest.get(sha256)
            if current is None or candidate.last_modified > current.last_modified:
                latest[sha256] = candidate
    return latest


def _load_previous_audit(path: Path | None) -> dict[tuple[str, str], dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    valid: dict[tuple[str, str], dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        sha256 = str(record.get("correlation_key") or "").lower()
        task_id = str(record.get("task_id") or "")
        if record.get("state") == "valid" and len(sha256) == 64 and task_id:
            valid[(sha256, task_id)] = record
    return valid


def _transfer_config(downloads: int) -> TransferConfig:
    return TransferConfig(
        multipart_threshold=16 * 1024 * 1024,
        multipart_chunksize=16 * 1024 * 1024,
        max_request_concurrency=max(1, downloads),
        max_submission_concurrency=min(8, max(1, downloads)),
        num_download_attempts=5,
    )


def _download_manifests(
    manager: TransferManager,
    bucket: str,
    candidates: list[S3Candidate],
    root: Path,
) -> dict[str, dict[str, Any]]:
    futures: list[tuple[S3Candidate, Path, Any]] = []
    for candidate in candidates:
        destination = root / f"{candidate.sha256}.json"
        key = f"results/tasks/{candidate.task_id}/manifest.json"
        futures.append(
            (
                candidate,
                destination,
                manager.download(bucket, key, str(destination)),
            )
        )

    manifests: dict[str, dict[str, Any]] = {}
    for candidate, destination, future in futures:
        try:
            future.result()
        except Exception as error:
            raise RuntimeError(
                f"{candidate.sha256}: falha ao baixar "
                f"results/tasks/{candidate.task_id}/manifest.json"
            ) from error
        manifest = json.loads(destination.read_text(encoding="utf-8"))
        if manifest.get("status") != "completed":
            raise ValueError(
                f"{candidate.sha256}: status remoto não concluído "
                f"({manifest.get('status')!r})."
            )
        if str(manifest.get("task_id")) != candidate.task_id:
            raise ValueError(f"{candidate.sha256}: task_id inconsistente.")
        if str(manifest.get("correlation_key")).lower() != candidate.sha256:
            raise ValueError(f"{candidate.sha256}: correlation_key inconsistente.")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError(f"{candidate.sha256}: manifesto remoto sem artefatos.")
        manifests[candidate.sha256] = manifest
    return manifests


def _artifacts_to_validate(
    candidates: list[S3Candidate],
    manifests: dict[str, dict[str, Any]],
    previous: dict[tuple[str, str], dict[str, Any]],
) -> tuple[list[Artifact], set[str]]:
    artifacts: list[Artifact] = []
    reused: set[str] = set()
    for candidate in candidates:
        manifest = manifests[candidate.sha256]
        declared = manifest["artifacts"]
        previous_record = previous.get((candidate.sha256, candidate.task_id))
        if (
            previous_record is not None
            and int(previous_record.get("artifact_count") or -1) == len(declared)
            and int(previous_record.get("artifact_bytes_expected") or -1)
            == sum(int(item["bytes"]) for item in declared)
        ):
            reused.add(candidate.sha256)
            continue
        for item in declared:
            expected_sha256 = str(item.get("sha256") or "").lower()
            if len(expected_sha256) != 64:
                raise ValueError(
                    f"{candidate.sha256}: artefato sem SHA-256: {item.get('path')}"
                )
            artifacts.append(
                Artifact(
                    sha256=candidate.sha256,
                    task_id=candidate.task_id,
                    path=str(item["path"]),
                    expected_bytes=int(item["bytes"]),
                    expected_sha256=expected_sha256,
                )
            )
    return artifacts, reused


def _validate_artifacts(
    client: Any,
    bucket: str,
    artifacts: list[Artifact],
    downloads: int,
) -> dict[str, dict[str, int]]:
    validated: dict[str, dict[str, int]] = {}

    def validate_one(artifact: Artifact) -> tuple[Artifact, int]:
        try:
            response = client.get_object(Bucket=bucket, Key=artifact.key)
            body = response["Body"]
            digest = hashlib.sha256()
            actual_bytes = 0
            try:
                for chunk in iter(lambda: body.read(1024 * 1024), b""):
                    actual_bytes += len(chunk)
                    digest.update(chunk)
            finally:
                body.close()
        except Exception as error:
            raise RuntimeError(
                f"{artifact.sha256}: falha ao ler {artifact.key}"
            ) from error
        if actual_bytes != artifact.expected_bytes:
            raise ValueError(
                f"{artifact.sha256}: tamanho divergente em {artifact.path}: "
                f"{actual_bytes} != {artifact.expected_bytes}"
            )
        if digest.hexdigest() != artifact.expected_sha256:
            raise ValueError(
                f"{artifact.sha256}: SHA-256 divergente em {artifact.path}."
            )
        return artifact, actual_bytes

    with ThreadPoolExecutor(
        max_workers=max(1, downloads),
        thread_name_prefix="s3-sha256",
    ) as executor:
        for position, (artifact, actual_bytes) in enumerate(
            executor.map(validate_one, artifacts),
            start=1,
        ):
            record = validated.setdefault(
                artifact.sha256,
                {"artifact_count": 0, "artifact_bytes": 0},
            )
            record["artifact_count"] += 1
            record["artifact_bytes"] += actual_bytes
            if position % 512 == 0 or position == len(artifacts):
                print(
                    f"Validação S3: {position}/{len(artifacts)} artefatos",
                    flush=True,
                )
    return validated


def _source_uri(bucket: str, candidate: S3Candidate, manifest: dict[str, Any]) -> str:
    for artifact in manifest["artifacts"]:
        if (
            str(artifact.get("sha256") or "").lower() == candidate.sha256
            and str(artifact.get("path") or "").casefold().endswith(".pdf")
        ):
            return (
                f"s3://{bucket}/results/tasks/{candidate.task_id}/"
                f"{artifact['path']}"
            )
    return f"s3://{bucket}/results/tasks/{candidate.task_id}"


def _promoted_manifest(
    *,
    candidate: S3Candidate,
    remote: dict[str, Any],
    bucket: str,
    existing: ExtractionManifest | None,
    promoted_at: str,
) -> ExtractionManifest:
    document_id = candidate.sha256[:16]
    artifact_uri = f"s3://{bucket}/results/tasks/{candidate.task_id}"
    source_uri = _source_uri(bucket, candidate, remote)
    if existing is None:
        output_dir = settings.mineru_output_dir / "documents" / document_id
        manifest = ExtractionManifest(
            sha256=candidate.sha256,
            document_id=document_id,
            path=Path(source_uri),
            filename=f"{candidate.sha256}.pdf",
            output_dir=output_dir,
            status="ok",
            attempts=1,
            retry_count=0,
            row={
                "page_count": int(remote.get("page_count") or 0),
                "canonical_source": "s3_promotion",
            },
        )
    else:
        manifest = existing

    controller = dict(manifest.controller)
    controller["canonical_source"] = {
        "kind": "s3_promotion",
        "bucket": bucket,
        "index_key": candidate.index_key,
        "index_last_modified": candidate.last_modified.astimezone(
            timezone.utc
        ).isoformat(),
        "promoted_at": promoted_at,
        "validation": "declared-size-and-sha256",
        "reason": "resultado recente ausente dos Volumes Disk atuais",
    }
    history = list(manifest.task_history)
    if not any(
        item.get("event") == "canonical_s3_promotion"
        and item.get("task_id") == candidate.task_id
        for item in history
        if isinstance(item, dict)
    ):
        history.append(
            {
                "event": "canonical_s3_promotion",
                "task_id": candidate.task_id,
                "at": promoted_at,
                "artifact_uri": artifact_uri,
            }
        )
    return manifest.model_copy(
        update={
            "status": "ok",
            "task_id": candidate.task_id,
            "correlation_key": candidate.sha256,
            "duration_seconds": remote.get("duration_seconds"),
            "source_uri": source_uri,
            "artifact_uri": artifact_uri,
            "artifacts": list(remote["artifacts"]),
            "task_history": history,
            "controller": controller,
            "error": None,
            "updated_at": promoted_at,
            "pod_id": remote.get("pod_id") or manifest.pod_id,
        }
    )


def _canonical_reconciliation(extra: ExtractionManifest) -> dict[str, Any]:
    inventory_summary = json.loads(
        (settings.data_dir / "audit" / "inventory" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    items = _load_manifest(Path(inventory_summary["extraction_manifest_path"]))
    items.append(
        WorkItem(
            position=len(items),
            document=DocumentRecord(
                sha256=extra.sha256,
                document_id=extra.document_id,
                path=extra.path,
                filename=extra.filename,
                size_bytes=next(
                    (
                        int(item["bytes"])
                        for item in extra.artifacts
                        if str(item.get("sha256") or "").lower() == extra.sha256
                    ),
                    None,
                ),
                page_count=int(extra.row.get("page_count") or 0) or None,
            ),
            output_dir=extra.output_dir,
            row=dict(extra.row),
        )
    )
    manifests = ManifestStore(settings.mineru_output_dir / "manifests")
    frame = _reconcile_manifests(items, manifests, settings.mineru_output_dir)
    return _write_reconciliation_summary(frame, settings.mineru_output_dir)


def main() -> int:
    args = _parse_args()
    since = args.since
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    since = since.astimezone(timezone.utc)
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
    pod_tasks = _load_pod_tasks(args.pod_task_list)
    latest = _latest_s3_candidates(client, args.bucket)
    candidates = sorted(
        (
            candidate
            for sha256, candidate in latest.items()
            if sha256 not in pod_tasks
            and candidate.last_modified.astimezone(timezone.utc) >= since
        ),
        key=lambda item: item.sha256,
    )
    previous = _load_previous_audit(args.previous_audit)
    promoted_at = datetime.now(timezone.utc).isoformat()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_root = (
        settings.mineru_output_dir / "canonical-promotion" / run_id
    )
    report_root.mkdir(parents=True, exist_ok=True)
    for path in args.pod_task_list:
        shutil.copy2(path, report_root / path.name)

    report: dict[str, Any] = {
        "generated_at": promoted_at,
        "applied": False,
        "bucket": args.bucket,
        "endpoint_url": args.endpoint_url,
        "region": args.region,
        "since": since.isoformat(),
        "pod_task_count": len(pod_tasks),
        "s3_index_count": len(latest),
        "candidate_count": len(candidates),
        "candidate_min_time": min(
            (item.last_modified for item in candidates), default=None
        ),
        "candidate_max_time": max(
            (item.last_modified for item in candidates), default=None
        ),
    }
    _atomic_json(report_root / "report.json", report)

    transfer_config = _transfer_config(args.downloads)
    with tempfile.TemporaryDirectory(prefix="baseia-s3-promotion-") as temp_name:
        temporary = Path(temp_name)
        manifest_root = temporary / "manifests"
        manifest_root.mkdir()
        manager = TransferManager(client, transfer_config)
        try:
            remote_manifests = _download_manifests(
                manager,
                args.bucket,
                candidates,
                manifest_root,
            )
            artifacts, reused = _artifacts_to_validate(
                candidates,
                remote_manifests,
                previous,
            )
        finally:
            manager.shutdown()
        validation = _validate_artifacts(
            client,
            args.bucket,
            artifacts,
            args.downloads,
        )

    report.update(
        {
            "reused_previous_validation_count": len(reused),
            "new_validation_document_count": len(validation),
            "new_validation_artifact_count": len(artifacts),
            "new_validation_bytes": sum(
                artifact.expected_bytes for artifact in artifacts
            ),
            "validated_count": len(candidates),
            "candidate_sha256": [item.sha256 for item in candidates],
        }
    )
    _atomic_json(report_root / "report.json", report)
    print(
        f"Validados {len(candidates)} documentos S3-only: "
        f"{len(reused)} reutilizados da auditoria anterior e "
        f"{len(validation)} revalidados agora.",
        flush=True,
    )
    if not args.apply:
        print(f"Dry-run concluído: {report_root}", flush=True)
        return 0

    store = ManifestStore(settings.mineru_output_dir / "manifests")
    backup_root = report_root / "before"
    promoted: list[ExtractionManifest] = []
    extra: ExtractionManifest | None = None
    for candidate in candidates:
        manifest_path = store.path_for(candidate.sha256)
        existing: ExtractionManifest | None = None
        if manifest_path.exists():
            backup_path = backup_root / candidate.sha256[:2] / manifest_path.name
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest_path, backup_path)
            existing = ExtractionManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        promoted_manifest = _promoted_manifest(
            candidate=candidate,
            remote=remote_manifests[candidate.sha256],
            bucket=args.bucket,
            existing=existing,
            promoted_at=promoted_at,
        )
        store.save(promoted_manifest)
        promoted.append(promoted_manifest)
        if existing is None:
            if extra is not None:
                raise RuntimeError("Mais de um manifesto extra foi encontrado.")
            extra = promoted_manifest

    if extra is None:
        raise RuntimeError("O documento extra esperado não foi encontrado.")
    reconciliation = _canonical_reconciliation(extra)
    report.update(
        {
            "applied": True,
            "promoted_manifest_count": len(promoted),
            "extra_sha256": extra.sha256,
            "reconciliation": reconciliation,
        }
    )
    _atomic_json(report_root / "report.json", report)
    _atomic_json(
        settings.mineru_output_dir / "canonical-promotion" / "current.json",
        {
            "run_id": run_id,
            "report_path": str((report_root / "report.json").resolve()),
            "promoted_manifest_count": len(promoted),
            "extra_sha256": extra.sha256,
            "manifest_count": reconciliation["manifest_count"],
        },
    )
    print(
        f"Promoção aplicada: {len(promoted)} manifestos; "
        f"canônico={reconciliation['manifest_count']}.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
