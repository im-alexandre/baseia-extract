from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tarfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

import zstandard


@dataclass(frozen=True, slots=True)
class Dump:
    pod_id: str
    root: Path
    archive_parts: tuple[Path, ...]
    expected_files: dict[str, int]


class ConcatenatedReader:
    def __init__(self, paths: tuple[Path, ...]) -> None:
        self._paths = iter(paths)
        self._current: BinaryIO | None = None

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while size < 0 or remaining > 0:
            if self._current is None:
                try:
                    self._current = next(self._paths).open("rb")
                except StopIteration:
                    break
            chunk = self._current.read(-1 if size < 0 else remaining)
            if chunk:
                chunks.append(chunk)
                if size >= 0:
                    remaining -= len(chunk)
                continue
            self._current.close()
            self._current = None
        return b"".join(chunks)

    def close(self) -> None:
        if self._current is not None:
            self._current.close()
            self._current = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Valida snapshots completos dos volumes dos pods e materializa "
            "somente pacotes de tarefas integralmente verificadas."
        )
    )
    parser.add_argument(
        "--dump-root",
        type=Path,
        default=Path("data/mineru/pod-artifact-dumps"),
    )
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=Path("data/mineru/pod-volume-snapshots"),
    )
    parser.add_argument(
        "--documents-root",
        type=Path,
        default=Path("data/mineru/documents"),
    )
    parser.add_argument(
        "--report-root",
        type=Path,
        default=Path("data/mineru/pod-reconciliation"),
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> Path:
    normalized = value.removeprefix("./")
    relative = PurePosixPath(normalized)
    if (
        not normalized
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or ":" in relative.parts[0]
    ):
        raise ValueError(f"Caminho inseguro: {value!r}")
    return Path(*relative.parts)


def _read_inventory(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    with path.open("r", encoding="utf-8", newline="") as source:
        for number, raw_line in enumerate(source, start=1):
            line = raw_line.rstrip("\r\n")
            try:
                relative, size, _mtime = line.split("\t", 2)
                safe = _safe_relative(relative).as_posix()
                result[safe] = int(size)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"{path}:{number}: inventário inválido."
                ) from error
    return result


def _verify_checksum_manifest(root: Path) -> None:
    checksum_path = root / "SHA256SUMS"
    for number, raw_line in enumerate(
        checksum_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        expected, filename = raw_line.split(maxsplit=1)
        target = root / filename.lstrip("*")
        if not target.is_file():
            raise FileNotFoundError(f"{target} não existe.")
        actual = _sha256(target)
        if actual != expected.lower():
            raise ValueError(
                f"{checksum_path}:{number}: SHA-256 divergente em {target}."
            )


def _load_dumps(root: Path) -> list[Dump]:
    dumps: list[Dump] = []
    for pod_root in sorted(path for path in root.iterdir() if path.is_dir()):
        _verify_checksum_manifest(pod_root)
        before_path = pod_root / "FILES.before.tsv"
        after_path = pod_root / "FILES.after.tsv"
        if _sha256(before_path) != _sha256(after_path):
            raise ValueError(f"{pod_root.name}: inventário mudou durante o dump.")
        parts = tuple(sorted(pod_root.glob("mineru-results.tar.zst.part-*")))
        if not parts:
            raise FileNotFoundError(f"{pod_root.name}: arquivo não encontrado.")
        dumps.append(
            Dump(
                pod_id=pod_root.name,
                root=pod_root,
                archive_parts=parts,
                expected_files=_read_inventory(before_path),
            )
        )
    if not dumps:
        raise RuntimeError(f"Nenhum dump encontrado em {root.resolve()}.")
    return dumps


def _filesystem_inventory(root: Path) -> dict[str, int]:
    return {
        path.relative_to(root).as_posix(): path.stat().st_size
        for path in root.rglob("*")
        if path.is_file()
    }


def _extract_dump(dump: Dump, snapshot_root: Path) -> Path:
    destination = snapshot_root / dump.pod_id / "results"
    if destination.is_dir():
        actual = _filesystem_inventory(destination)
        if actual != dump.expected_files:
            raise ValueError(
                f"{dump.pod_id}: snapshot existente diverge do inventário."
            )
        return destination

    pod_root = destination.parent
    pod_root.mkdir(parents=True, exist_ok=True)
    staging = pod_root / f".extracting-{uuid.uuid4().hex}"
    staging.mkdir()
    concatenated = ConcatenatedReader(dump.archive_parts)
    try:
        with (
            zstandard.ZstdDecompressor().stream_reader(
                concatenated
            ) as decompressed,
            tarfile.open(fileobj=decompressed, mode="r|") as archive,
        ):
            archive.extractall(path=staging, filter="data")
        actual = _filesystem_inventory(staging)
        if actual != dump.expected_files:
            missing = sorted(dump.expected_files.keys() - actual.keys())[:10]
            extra = sorted(actual.keys() - dump.expected_files.keys())[:10]
            changed = sorted(
                path
                for path in dump.expected_files.keys() & actual.keys()
                if dump.expected_files[path] != actual[path]
            )[:10]
            raise ValueError(
                f"{dump.pod_id}: extração divergente; missing={missing}, "
                f"extra={extra}, changed={changed}."
            )
        os.replace(staging, destination)
    finally:
        concatenated.close()
        if staging.exists():
            shutil.rmtree(staging)
    return destination


def _load_task_manifest(task_dir: Path) -> dict[str, Any]:
    manifest_path = task_dir / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("status") != "completed":
        raise ValueError("status não é completed")
    correlation_key = str(payload.get("correlation_key") or "").lower()
    if len(correlation_key) != 64 or any(
        character not in "0123456789abcdef" for character in correlation_key
    ):
        raise ValueError("correlation_key inválida")
    if str(payload.get("task_id")) != task_dir.name:
        raise ValueError("task_id divergente")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("manifesto sem artefatos")
    return payload


def _validate_task(
    task_dir: Path,
    manifest: dict[str, Any],
    *,
    hash_files: bool,
) -> tuple[int, int]:
    count = 0
    total_bytes = 0
    for artifact in manifest["artifacts"]:
        relative = _safe_relative(str(artifact["path"]))
        target = task_dir / relative
        expected_bytes = int(artifact["bytes"])
        if not target.is_file():
            raise FileNotFoundError(f"artefato ausente: {relative.as_posix()}")
        actual_bytes = target.stat().st_size
        if actual_bytes != expected_bytes:
            raise ValueError(
                f"tamanho divergente em {relative.as_posix()}: "
                f"{actual_bytes} != {expected_bytes}"
            )
        if hash_files:
            expected_hash = str(artifact["sha256"]).lower()
            actual_hash = _sha256(target)
            if actual_hash != expected_hash:
                raise ValueError(
                    f"SHA-256 divergente em {relative.as_posix()}"
                )
        count += 1
        total_bytes += actual_bytes
    return count, total_bytes


def _link_or_copy(source: str, destination: str) -> str:
    try:
        os.link(source, destination)
        return destination
    except OSError:
        return shutil.copy2(source, destination)


def _materialize_task(
    task_dir: Path,
    documents_root: Path,
    manifest: dict[str, Any],
) -> str:
    correlation_key = str(manifest["correlation_key"]).lower()
    destination = documents_root / correlation_key[:16]
    if destination.is_dir():
        _validate_task(destination, manifest, hash_files=True)
        return "reused"
    if destination.exists():
        raise FileExistsError(f"destino não é diretório: {destination}")

    documents_root.mkdir(parents=True, exist_ok=True)
    staging = (
        documents_root
        / f".materializing-{correlation_key[:16]}-{uuid.uuid4().hex}"
    )
    try:
        shutil.copytree(task_dir, staging, copy_function=_link_or_copy)
        _validate_task(staging, manifest, hash_files=True)
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return "materialized"


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    args = _parse_args()
    dumps = _load_dumps(args.dump_root.resolve())
    snapshots: list[tuple[Dump, Path]] = []
    for dump in dumps:
        print(f"Extraindo/verificando snapshot {dump.pod_id}...", flush=True)
        snapshots.append(
            (dump, _extract_dump(dump, args.snapshot_root.resolve()))
        )

    rows: list[dict[str, Any]] = []
    seen_sha256: dict[str, str] = {}
    for dump, snapshot in snapshots:
        tasks_root = snapshot / "tasks"
        task_dirs = sorted(path for path in tasks_root.iterdir() if path.is_dir())
        for position, task_dir in enumerate(task_dirs, start=1):
            row: dict[str, Any] = {
                "pod_id": dump.pod_id,
                "task_id": task_dir.name,
                "sha256": None,
                "status": "error",
                "artifact_count": 0,
                "artifact_bytes": 0,
                "materialization": None,
                "error": None,
            }
            try:
                manifest = _load_task_manifest(task_dir)
                sha256 = str(manifest["correlation_key"]).lower()
                row["sha256"] = sha256
                previous_task = seen_sha256.get(sha256)
                if previous_task is not None:
                    raise ValueError(
                        f"SHA duplicada nas tasks {previous_task} e "
                        f"{task_dir.name}"
                    )
                seen_sha256[sha256] = task_dir.name
                artifact_count, artifact_bytes = _validate_task(
                    task_dir,
                    manifest,
                    hash_files=True,
                )
                row["artifact_count"] = artifact_count
                row["artifact_bytes"] = artifact_bytes
                row["materialization"] = _materialize_task(
                    task_dir,
                    args.documents_root.resolve(),
                    manifest,
                )
                row["status"] = "ok"
            except Exception as error:  # noqa: BLE001 - registra por tarefa
                row["error"] = f"{type(error).__name__}: {error}"
            rows.append(row)
            if position % 100 == 0 or position == len(task_dirs):
                errors = sum(item["status"] != "ok" for item in rows)
                print(
                    f"{dump.pod_id}: {position}/{len(task_dirs)} "
                    f"(erros acumulados={errors})",
                    flush=True,
                )

    now = datetime.now(UTC).isoformat()
    report_root = args.report_root.resolve()
    report_root.mkdir(parents=True, exist_ok=True)
    csv_path = report_root / "tasks.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    ok_rows = [row for row in rows if row["status"] == "ok"]
    report = {
        "generated_at": now,
        "dump_count": len(dumps),
        "source_file_count": sum(len(dump.expected_files) for dump in dumps),
        "source_bytes": sum(
            sum(dump.expected_files.values()) for dump in dumps
        ),
        "task_count": len(rows),
        "valid_task_count": len(ok_rows),
        "error_task_count": len(rows) - len(ok_rows),
        "artifact_count": sum(row["artifact_count"] for row in ok_rows),
        "artifact_bytes": sum(row["artifact_bytes"] for row in ok_rows),
        "materialized_count": sum(
            row["materialization"] == "materialized" for row in ok_rows
        ),
        "reused_count": sum(
            row["materialization"] == "reused" for row in ok_rows
        ),
        "documents_directory_count": sum(
            path.is_dir()
            and not path.name.startswith(".")
            for path in args.documents_root.resolve().iterdir()
        ),
        "tasks_csv": str(csv_path),
        "snapshots": {
            dump.pod_id: str(snapshot)
            for dump, snapshot in snapshots
        },
    }
    _atomic_json(report_root / "summary.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 1 if report["error_task_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
