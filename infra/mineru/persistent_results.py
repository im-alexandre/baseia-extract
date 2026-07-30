"""Durable result packages for the MinerU 3.4.4 router.

The upstream router intentionally keeps task metadata in memory and starts each
local worker with a temporary output directory.  This compatibility layer keeps
the public MinerU HTTP API unchanged while recording task metadata and copying
completed artifacts to the Network Volume independently from result downloads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio
import catalog_client
import s3_results
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_never,
    wait_exponential,
)

ROOT_ENV = "MINERU_PERSISTENT_RESULTS_ROOT"
DEFAULT_ROOT = "/workspace/results"
WORK_ROOT_ENV = "MINERU_LOCAL_WORK_ROOT"
DEFAULT_WORK_ROOT = "/tmp/mineru-active"


class VolumeUnavailable(RuntimeError):
    """The shared Network Volume cannot be used for an idempotency decision."""


class PersistenceBackpressure(RuntimeError):
    """The pod must stop accepting new work until persistence catches up."""


def _root() -> Path:
    root = Path(os.environ.get(ROOT_ENV, DEFAULT_ROOT)).resolve()
    if root != Path(DEFAULT_ROOT):
        raise RuntimeError(f"{ROOT_ENV} deve ser exatamente {DEFAULT_ROOT}.")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _work_root() -> Path:
    """Return the container-local root used by MinerU workers."""
    root = Path(os.environ.get(WORK_ROOT_ENV, DEFAULT_WORK_ROOT)).resolve()
    if root == Path("/workspace") or Path("/workspace") in root.parents:
        raise RuntimeError(f"{WORK_ROOT_ENV} não pode apontar para /workspace.")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _owner() -> str:
    value = os.environ.get("RUNPOD_POD_ID") or os.environ.get("POD_ID") or os.environ.get("HOSTNAME") or "unknown-pod"
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


def persistence_admission_status() -> dict[str, Any]:
    max_unpersisted = int(
        os.environ.get("MINERU_MAX_UNPERSISTED_TASKS", "256")
    )
    min_free_gib = float(
        os.environ.get("MINERU_MIN_FREE_DISK_GIB", "10")
    )
    min_free_percent = float(
        os.environ.get("MINERU_MIN_FREE_DISK_PERCENT", "10")
    )
    if max_unpersisted < 1:
        raise ValueError(
            "MINERU_MAX_UNPERSISTED_TASKS deve ser positivo."
        )
    if min_free_gib < 0 or not 0 <= min_free_percent < 100:
        raise ValueError(
            "Limites de disco da persistência são inválidos."
        )
    manifests_root = _root() / "manifests" / _owner()
    try:
        manifest_paths = tuple(manifests_root.glob("*.json"))
    except OSError as error:
        raise VolumeUnavailable(
            "não foi possível medir o backlog de persistência"
        ) from error
    unpersisted = 0
    for path in manifest_paths:
        manifest = _read_manifest(path)
        if manifest is None:
            unpersisted += 1
            continue
        if (
            not manifest.get("persisted_at")
            and str(manifest.get("status") or "").casefold()
            not in {"failed", "cancelled"}
        ):
            unpersisted += 1

    try:
        usage = shutil.disk_usage(_work_root())
    except OSError as error:
        raise VolumeUnavailable(
            "não foi possível medir o disco local de trabalho"
        ) from error
    required_free_bytes = max(
        int(min_free_gib * 1024**3),
        int(usage.total * min_free_percent / 100),
    )
    reasons: list[str] = []
    if unpersisted >= max_unpersisted:
        reasons.append(
            f"backlog={unpersisted} >= limite={max_unpersisted}"
        )
    if usage.free < required_free_bytes:
        reasons.append(
            f"disco_livre={usage.free} < mínimo={required_free_bytes}"
        )
    return {
        "accepting": not reasons,
        "owner": _owner(),
        "unpersisted_tasks": unpersisted,
        "max_unpersisted_tasks": max_unpersisted,
        "disk_total_bytes": usage.total,
        "disk_free_bytes": usage.free,
        "required_free_bytes": required_free_bytes,
        "reasons": reasons,
    }


def require_persistence_capacity() -> dict[str, Any]:
    status = persistence_admission_status()
    if not status["accepting"]:
        raise PersistenceBackpressure(
            "; ".join(str(reason) for reason in status["reasons"])
        )
    return status


def _manifest_path(task_id: str, owner: str | None = None) -> Path:
    return _root() / "manifests" / (owner or _owner()) / f"{task_id}.json"


def _correlation_index_dir(correlation_key: str) -> Path:
    return _root() / "by-sha" / correlation_key[:2] / correlation_key


def _completion_marker_path(upstream_task_id: str) -> Path:
    return _root() / "completion-markers" / _owner() / f"{upstream_task_id}.json"


def _log_volume_retry(retry_state: Any) -> None:
    error = retry_state.outcome.exception() if retry_state.outcome else None
    print(
        "[mineru-persistence] Network Volume indisponível; "
        f"tentativa={retry_state.attempt_number} | "
        f"erro={type(error).__name__}: {error}",
        file=sys.stderr,
        flush=True,
    )


def _atomic_json_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    for attempt in Retrying(
        retry=retry_if_exception_type(OSError),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_never,
        before_sleep=_log_volume_retry,
        reraise=True,
    ):
        with attempt:
            _atomic_json_once(path, payload)


def _atomic_json_fail_closed(path: Path, payload: dict[str, Any]) -> None:
    try:
        _atomic_json_once(path, payload)
    except OSError as error:
        raise VolumeUnavailable(f"não foi possível gravar {path}") from error


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_manifest_strict(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise VolumeUnavailable(f"não foi possível ler {path}") from error
    if not isinstance(value, dict):
        raise VolumeUnavailable(f"manifesto inválido: {path}")
    return value


def register_task(
    task: Any,
    *,
    idempotency_key: str | None = None,
    request_metadata: dict[str, str] | None = None,
) -> None:
    """Persist the router/upstream mapping immediately after submission."""
    task_id = str(task.task_id)
    server_id = str(task.upstream_server_id)
    upstream_task_id = str(task.upstream_task_id)
    source_dir = _work_root() / server_id / "output" / upstream_task_id
    gpu_id = server_id.removeprefix("local-gpu-") if server_id.startswith("local-gpu-") else None
    source_names = [str(name) for name in task.file_names]
    correlation_key = next(
        (name for name in source_names if len(name) == 64 and all(char in "0123456789abcdef" for char in name.lower())),
        None,
    )
    metadata = dict(request_metadata or {})
    manifest = {
            "schema_version": 1,
            "task_id": task_id,
            "upstream_task_id": upstream_task_id,
            "upstream_server_id": server_id,
            "upstream_base_url": str(task.upstream_base_url).rstrip("/"),
            "backend": str(task.backend),
            "pod_id": os.environ.get("RUNPOD_POD_ID") or os.environ.get("POD_ID") or os.environ.get("HOSTNAME"),
            "gpu_id": gpu_id,
            "source_filenames": source_names,
            "correlation_key": correlation_key,
            "idempotency_key": idempotency_key,
            "content_sha256": metadata.get("content_sha256") or correlation_key,
            "document_revision_id": metadata.get("document_revision_id"),
            "artifact_prefix": metadata.get("artifact_prefix"),
            "stage": metadata.get("stage") or "extract",
            "processor": metadata.get("processor") or "mineru",
            "processor_version": metadata.get("processor_version"),
            "config_hash": metadata.get("config_hash"),
            "stage_run_id": metadata.get("stage_run_id"),
            "lease_owner": metadata.get("lease_owner"),
            "lease_attempt": metadata.get("lease_attempt"),
            "status": str(task.status),
            "created_at": str(task.created_at),
            "submitted_at": datetime.now(UTC).isoformat(),
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error": task.error,
            "source_dir": str(source_dir),
            "package_dir": f"tasks/{task_id}",
            "persisted_at": None,
    }
    manifest_path = _manifest_path(task_id)
    write = _atomic_json_fail_closed if idempotency_key is not None else _atomic_json
    write(manifest_path, manifest)
    index_keys = {
        key
        for key in (correlation_key, idempotency_key)
        if key is not None
    }
    for index_key in index_keys:
        write(
            _correlation_index_dir(index_key) / f"{task_id}.json",
            {
                "task_id": task_id,
                "owner": _owner(),
                "manifest_path": manifest_path.relative_to(_root()).as_posix(),
                "submitted_at": manifest["submitted_at"],
            },
        )
    catalog_client.transition(
        str(manifest.get("stage_run_id") or "") or None,
        "processing",
        lease_owner=str(manifest.get("lease_owner") or ""),
        lease_attempt=int(manifest.get("lease_attempt") or 0),
    )


def find_by_correlation(correlation_key: str) -> list[dict[str, Any]]:
    """Return task records for the SHA-256 upload identity, newest first."""
    if len(correlation_key) != 64 or any(char not in "0123456789abcdef" for char in correlation_key.lower()):
        return []
    correlation_key = correlation_key.lower()
    matches: list[dict[str, Any]] = []
    try:
        index_paths = tuple(_correlation_index_dir(correlation_key).glob("*.json"))
    except OSError as error:
        raise VolumeUnavailable("não foi possível listar índice SHA") from error
    for path in index_paths:
        index = _read_manifest_strict(path)
        if index is None or not isinstance(index.get("task_id"), str):
            continue
        relative_path = index.get("manifest_path")
        if not isinstance(relative_path, str):
            raise VolumeUnavailable(f"índice inválido: {path}")
        manifest_path = (_root() / relative_path).resolve()
        if not manifest_path.is_relative_to(_root()) or manifest_path.name != f"{index['task_id']}.json":
            raise VolumeUnavailable(f"índice inválido: {path}")
        manifest = _read_manifest_strict(manifest_path)
        if manifest is not None and manifest.get("correlation_key") == correlation_key:
            matches.append(manifest)
    return sorted(matches, key=lambda item: str(item.get("submitted_at", "")), reverse=True)


def find_by_idempotency_key(key: str) -> dict[str, Any] | None:
    """Find the deterministic external task recorded for an Idempotency-Key."""
    if len(key) != 64 or any(char not in "0123456789abcdef" for char in key.lower()):
        return None
    key = key.lower()
    try:
        index_paths = tuple(_correlation_index_dir(key).glob("*.json"))
    except OSError as error:
        raise VolumeUnavailable("não foi possível listar índice SHA") from error
    for path in index_paths:
        index = _read_manifest_strict(path)
        if index is None or index.get("task_id") != key:
            continue
        relative_path = index.get("manifest_path")
        if not isinstance(relative_path, str):
            raise VolumeUnavailable(f"índice inválido: {path}")
        manifest_path = (_root() / relative_path).resolve()
        if not manifest_path.is_relative_to(_root()):
            raise VolumeUnavailable(f"índice fora do volume: {path}")
        manifest = _read_manifest_strict(manifest_path)
        if manifest is not None and manifest.get("idempotency_key") == key:
            return manifest

    # The task manifest is written before its secondary by-sha pointer. If
    # the pointer write was interrupted, recover by deterministic filename
    # across the small owner directory set and repair the index atomically.
    try:
        manifest_paths = tuple((_root() / "manifests").glob(f"*/{key}.json"))
    except OSError as error:
        raise VolumeUnavailable("não foi possível listar manifestos idempotentes") from error
    candidates = [
        (path, manifest)
        for path in manifest_paths
        if (manifest := _read_manifest_strict(path)) is not None
        and manifest.get("task_id") == key
        and manifest.get("idempotency_key") == key
    ]
    if not candidates:
        return None
    manifest_path, manifest = max(
        candidates,
        key=lambda candidate: (
            bool(candidate[1].get("persisted_at")),
            str(candidate[1].get("submitted_at", "")),
        ),
    )
    _atomic_json_fail_closed(
        _correlation_index_dir(key) / f"{key}.json",
        {
            "task_id": key,
            "owner": manifest_path.parent.name,
            "manifest_path": manifest_path.relative_to(_root()).as_posix(),
            "submitted_at": manifest.get("submitted_at"),
        },
    )
    return manifest
    return None


def find_or_alias_idempotency_key(key: str) -> dict[str, Any] | None:
    """Return a deterministic record, aliasing one unambiguous legacy task."""
    current = find_by_idempotency_key(key)
    if current is not None:
        return current
    try:
        index_paths = tuple(_correlation_index_dir(key).glob("*.json"))
    except OSError as error:
        raise VolumeUnavailable("não foi possível listar índice SHA") from error
    legacy: list[dict[str, Any]] = []
    for path in index_paths:
        index = _read_manifest_strict(path)
        if index is None or not isinstance(index.get("manifest_path"), str):
            continue
        manifest_path = (_root() / index["manifest_path"]).resolve()
        if not manifest_path.is_relative_to(_root()):
            raise VolumeUnavailable(f"índice fora do volume: {path}")
        manifest = _read_manifest_strict(manifest_path)
        if manifest is not None and manifest.get("correlation_key") == key:
            legacy.append(manifest)
    if len(legacy) != 1:
        return None
    source = legacy[0]
    if source.get("task_id") == key:
        return None
    if not (
        source.get("status") == "completed"
        and source.get("persisted_at")
        and (
            source.get("package_dir")
            or isinstance(source.get("result_ref"), dict)
        )
        and isinstance(source.get("artifacts"), list)
        and source["artifacts"]
    ):
        raise VolumeUnavailable(
            "tarefa legada ainda ativa; aguarde a reconciliação pelo task_id original"
        )
    alias = {
        **source,
        "task_id": key,
        "idempotency_key": key,
        "legacy_task_id": source["task_id"],
    }
    alias_path = _manifest_path(key)
    _atomic_json_fail_closed(alias_path, alias)
    _atomic_json_fail_closed(
        _correlation_index_dir(key) / f"{key}.json",
        {
            "task_id": key,
            "owner": _owner(),
            "manifest_path": alias_path.relative_to(_root()).as_posix(),
            "submitted_at": alias.get("submitted_at"),
        },
    )
    return alias


def record_worker_completion(task: Any) -> None:
    """Durably record the official worker terminal state before upload cleanup."""
    if str(task.status) != "completed":
        return
    _atomic_json(
        _completion_marker_path(str(task.task_id)),
        {
            "upstream_task_id": str(task.task_id),
            "status": "completed",
            "output_dir": str(task.output_dir),
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "recorded_at": datetime.now(UTC).isoformat(),
        },
    )


def _artifact_paths(source: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(source.rglob("*")):
        if path.is_file():
            relative = path.relative_to(source)
            if (
                relative.parts
                and relative.parts[0].casefold() == "uploads"
                and relative.suffix.casefold() == ".pdf"
            ):
                # O PDF fonte já possui uma key canônica no object storage.
                # O diretório uploads é apenas entrada efêmera do MinerU.
                continue
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            files.append(
                {
                    "path": relative.as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": digest.hexdigest(),
                }
            )
    return files


def _page_count(source: Path) -> int | None:
    """Read the official middle JSON without assuming a single schema shape."""
    middle = next(iter(sorted(source.rglob("*_middle.json"))), None)
    if middle is None:
        return None
    try:
        payload = json.loads(middle.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return None
    for key in ("page_count", "pages", "pdf_info", "page_info"):
        value = payload.get(key)
        if isinstance(value, int) and value >= 0:
            return value
        if isinstance(value, list):
            return len(value)
    return None


def _duration_seconds(started_at: object, completed_at: object) -> float | None:
    if not isinstance(started_at, str) or not isinstance(completed_at, str):
        return None
    try:
        started = datetime.fromisoformat(started_at)
        completed = datetime.fromisoformat(completed_at)
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    if completed.tzinfo is None:
        completed = completed.replace(tzinfo=UTC)
    return max(0.0, round((completed - started).total_seconds(), 3))


def _has_complete_result(source: Path) -> bool:
    if not source.is_dir():
        return False
    middle = any(source.rglob("*_middle.json"))
    markdown = any(source.rglob("*.md"))
    content_list = any(
        path
        for pattern in ("*_content_list.json", "*_content_list_v2.json")
        for path in source.rglob(pattern)
    )
    return middle and markdown and content_list


def _validate_middle_assets(staging: Path, artifacts: list[dict[str, Any]]) -> None:
    content_lists = [
        item["path"]
        for item in artifacts
        if item["path"].endswith("_content_list.json")
        or item["path"].endswith("_content_list_v2.json")
    ]
    if not content_lists:
        raise RuntimeError("resultado sem content_list solicitado pelo contrato")

    def image_paths(value: Any) -> list[str]:
        if isinstance(value, list):
            return [path for item in value for path in image_paths(item)]
        if not isinstance(value, dict):
            return []
        found: list[str] = []
        for key, item in value.items():
            if key == "image_path" and isinstance(item, str) and item:
                found.append(item)
            found.extend(image_paths(item))
        return found

    for middle in staging.rglob("*_middle.json"):
        try:
            payload = json.loads(middle.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"middle.json inválido: {middle}") from error
        for image_path in image_paths(payload):
            candidates = (
                (middle.parent / image_path).resolve(),
                (middle.parent / "images" / Path(image_path).name).resolve(),
            )
            if not any(
                candidate.is_relative_to(staging.resolve()) and candidate.is_file()
                for candidate in candidates
            ):
                raise RuntimeError(
                    f"image_path ausente no pacote: {image_path} ({middle.name})"
                )


def _copy_artifacts_once(
    source: Path, staging: Path, artifacts: list[dict[str, Any]]
) -> None:
    """Copy each file through a local temp name so a resumed staging is safe."""
    staging.mkdir(parents=True, exist_ok=True)
    for artifact in artifacts:
        relative = Path(str(artifact["path"]))
        origin = source / relative
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.copying")
        try:
            shutil.copy2(origin, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)


def _validate_artifacts(
    package: Path, expected: list[dict[str, Any]]
) -> None:
    expected_by_path = {str(item["path"]): item for item in expected}
    actual = [
        item
        for item in _artifact_paths(package)
        if item["path"] != "manifest.json" or "manifest.json" in expected_by_path
    ]
    actual_by_path = {str(item["path"]): item for item in actual}
    if actual_by_path != expected_by_path:
        raise RuntimeError("hashes ou arquivos do pacote publicado não conferem")
    if not any(path.endswith("_middle.json") for path in actual_by_path):
        raise RuntimeError("resultado sem middle.json")
    if not any(path.endswith(".md") for path in actual_by_path):
        raise RuntimeError("resultado sem Markdown")
    _validate_middle_assets(package, actual)


def _published_package(manifest: dict[str, Any], final_dir: Path) -> dict[str, Any] | None:
    packaged = _read_manifest(final_dir / "manifest.json")
    if packaged is None or not isinstance(packaged.get("artifacts"), list):
        return None
    try:
        _validate_artifacts(
            final_dir,
            [item for item in packaged["artifacts"] if isinstance(item, dict)],
        )
    except (OSError, RuntimeError, KeyError, TypeError):
        return None
    return packaged


def _persist_completed_once(manifest: dict[str, Any]) -> bool:
    if manifest.get("status") != "completed":
        return False
    source = Path(str(manifest["source_dir"]))
    if not _has_complete_result(source):
        return False

    if s3_results.enabled():
        artifacts = _artifact_paths(source)
        _validate_artifacts(source, artifacts)
        enriched = {
            **manifest,
            "page_count": _page_count(source),
            "duration_seconds": _duration_seconds(
                manifest.get("started_at"),
                manifest.get("completed_at"),
            ),
        }
        package_manifest = s3_results.publish(
            source,
            enriched,
            artifacts,
        )
        manifest.update(package_manifest)
        manifest["status"] = "completed"
        _atomic_json(_manifest_path(str(manifest["task_id"])), manifest)
        shutil.rmtree(source)
        return True

    task_id = str(manifest["task_id"])
    root = _root()
    final_dir = root / "tasks" / task_id
    if final_dir.exists():
        packaged = _published_package(manifest, final_dir)
        if packaged is None:
            raise RuntimeError(
                f"pacote já publicado inválido; preservado para recuperação: {final_dir}"
            )
        manifest.update(
            {
                key: value
                for key, value in packaged.items()
                if key in {"artifacts", "file_count", "artifact_bytes", "page_count", "duration_seconds", "persisted_at"}
            }
        )
        manifest["status"] = "completed"
        manifest["persisted_at"] = manifest.get("persisted_at") or datetime.now(UTC).isoformat()
        _atomic_json(_manifest_path(task_id), manifest)
        shutil.rmtree(source)
        return True

    # A deterministic staging location makes an interrupted Network Volume
    # copy resumable. It is never exposed as a completed task.
    staging = root / ".staging" / task_id
    artifacts = _artifact_paths(source)
    _validate_artifacts(source, artifacts)
    _copy_artifacts_once(source, staging, artifacts)
    _validate_artifacts(staging, artifacts)
    package_manifest = {
        **manifest,
        "status": "completed",
        "persisted_at": datetime.now(UTC).isoformat(),
        "file_count": len(artifacts),
        "artifact_bytes": sum(item["bytes"] for item in artifacts),
        "page_count": _page_count(staging),
        "duration_seconds": _duration_seconds(
            manifest.get("started_at"), manifest.get("completed_at")
        ),
        "artifacts": artifacts,
    }
    _atomic_json(staging / "manifest.json", package_manifest)
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    if final_dir.exists():
        raise RuntimeError(f"pacote publicado durante a cópia; preservando staging: {final_dir}")
    os.replace(staging, final_dir)
    _atomic_json(_manifest_path(task_id), package_manifest)
    # The origin is only eligible for removal after the complete package is
    # atomically visible and the durable task manifest has been updated.
    shutil.rmtree(source)
    return True


def _persist_completed(manifest: dict[str, Any]) -> bool:
    """Persist with unbounded retry for transient Network Volume failures."""
    for attempt in Retrying(
        retry=retry_if_exception_type(OSError),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_never,
        before_sleep=_log_volume_retry,
        reraise=True,
    ):
        with attempt:
            return _persist_completed_once(manifest)
    raise AssertionError("retry infinito terminou inesperadamente")


def _upstream_status(manifest: dict[str, Any]) -> dict[str, Any] | None:
    url = f"{str(manifest['upstream_base_url']).rstrip('/')}/tasks/{manifest['upstream_task_id']}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _completion_marker(manifest: dict[str, Any]) -> dict[str, Any] | None:
    marker = _read_manifest(_completion_marker_path(str(manifest["upstream_task_id"])))
    if marker is None or marker.get("status") != "completed":
        return None
    if marker.get("output_dir") != manifest.get("source_dir"):
        return None
    return marker


def _reconcile_path(path: Path) -> tuple[int, int]:
    manifest = _read_manifest(path)
    if manifest is None or manifest.get("persisted_at"):
        return 0, 0
    heartbeat_at = manifest.get("lease_heartbeat_at")
    heartbeat_due = True
    if isinstance(heartbeat_at, str):
        try:
            heartbeat_due = (
                datetime.now(UTC)
                - datetime.fromisoformat(heartbeat_at)
            ).total_seconds() >= 60
        except ValueError:
            heartbeat_due = True
    if heartbeat_due and manifest.get("stage_run_id"):
        catalog_client.heartbeat(
            str(manifest["stage_run_id"]),
            lease_owner=str(manifest.get("lease_owner") or ""),
            lease_attempt=int(manifest.get("lease_attempt") or 0),
        )
        manifest["lease_heartbeat_at"] = datetime.now(
            UTC
        ).isoformat()
        _atomic_json(path, manifest)
    upstream_base_url = str(manifest.get("upstream_base_url") or "")
    status = (
        None
        if upstream_base_url.startswith("catalog://")
        else _upstream_status(manifest)
    )
    if status is None:
        status = _completion_marker(manifest)
        if status is None:
            return 0, 0
    manifest["status"] = str(
        status.get("status", manifest.get("status", "unknown"))
    )
    manifest["started_at"] = status.get(
        "started_at",
        manifest.get("started_at"),
    )
    manifest["completed_at"] = status.get(
        "completed_at",
        manifest.get("completed_at"),
    )
    manifest["error"] = status.get("error", manifest.get("error"))
    manifest["duration_seconds"] = _duration_seconds(
        manifest.get("started_at"),
        manifest.get("completed_at"),
    )
    failed = int(manifest["status"] == "failed")
    if failed:
        catalog_client.fail(
            str(manifest.get("stage_run_id") or "") or None,
            error_type="MinerUTaskFailed",
            message=str(manifest.get("error") or "MinerU task failed"),
            retryable=False,
            lease_owner=str(manifest.get("lease_owner") or ""),
            lease_attempt=int(manifest.get("lease_attempt") or 0),
        )
    _atomic_json(path, manifest)
    completed = int(
        manifest["status"] == "completed"
        and _persist_completed(manifest)
    )
    return completed, failed


async def _reconcile_paths(paths: tuple[Path, ...]) -> tuple[int, int]:
    limiter = anyio.CapacityLimiter(
        max(
            1,
            int(os.environ.get("MINERU_PERSISTENCE_CONCURRENCY", "4")),
        )
    )
    results: list[tuple[int, int]] = []

    async def reconcile(path: Path) -> None:
        result = await anyio.to_thread.run_sync(
            _reconcile_path,
            path,
            limiter=limiter,
        )
        results.append(result)

    async with anyio.create_task_group() as tasks:
        for path in paths:
            tasks.start_soon(reconcile, path)
    return (
        sum(item[0] for item in results),
        sum(item[1] for item in results),
    )


def reconcile_once() -> tuple[int, int]:
    """Persist completed outputs concurrently and idempotently."""
    paths = tuple(
        sorted((_root() / "manifests" / _owner()).glob("*.json"))
    )
    return anyio.run(_reconcile_paths, paths)


def watch(interval: float) -> None:
    while True:
        try:
            reconcile_once()
        except Exception as error:  # noqa: BLE001 - watcher deve sobreviver
            # A malformed result must not take the router down. OSErrors in
            # publication already retry forever above; preserve any staging
            # and retry validation failures on the next sweep.
            print(
                f"[mineru-persistence] reconciliação adiada: {type(error).__name__}: {error}",
                file=sys.stderr,
                flush=True,
            )
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()
    if args.watch:
        watch(max(1.0, args.interval))
    else:
        print(json.dumps(dict(zip(("completed", "failed"), reconcile_once()))))


if __name__ == "__main__":
    main()
