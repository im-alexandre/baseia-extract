from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd
from filelock import FileLock, Timeout
from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .document_manifest import write_document_manifest
from .identity import (
    CATALOG_NAMESPACE,
    canonical_json_sha256,
    collection_uuid,
    document_uuid,
    revision_uuid,
)
from .inventory import INVENTORY_COLUMNS
from .layout import document_layout
from .settings import settings
from .storage import file_sha256

PLAN_VERSION = 1
EXPECTED_VALID_COUNTS = {
    "snptee": 2149,
    "ciencia-de-dados": 179,
    "revista-ppgcc-uerj": 201,
    "minha-dissertacao": 62,
    "diversos": 1449,
}
EXPECTED_INVALID_COUNT = 8
CANONICAL_FILES = (
    "document_ir.json",
    "structure.json",
    "document.md",
    "render.json",
)


@dataclass(frozen=True, slots=True)
class SourceRoot:
    collection: str
    slug: str
    root: Path
    preserve_tree: bool
    normalize_whitespace: bool = False


SOURCE_ROOTS = (
    SourceRoot(
        collection="SNPTEE",
        slug="snptee",
        root=Path(
            r"D:\backups\snptee\SNPTEE_PDFs"
            r"\edicoes_anteriores_trabalhos_extraidos"
        ),
        preserve_tree=True,
        normalize_whitespace=True,
    ),
    SourceRoot(
        collection="Ciência de Dados",
        slug="ciencia-de-dados",
        root=Path(r"D:\backups\livros-data-science"),
        preserve_tree=False,
    ),
    SourceRoot(
        collection="Revista PPGCC UERJ",
        slug="revista-ppgcc-uerj",
        root=Path(r"D:\backups\revista-ppgcc"),
        preserve_tree=False,
    ),
    SourceRoot(
        collection="Minha Dissertação",
        slug="minha-dissertacao",
        root=Path(r"D:\dissertacao\referencia_PLD_orientador"),
        preserve_tree=False,
    ),
    SourceRoot(
        collection="Minha Dissertação",
        slug="minha-dissertacao",
        root=Path(r"D:\dissertacao\referencias"),
        preserve_tree=False,
    ),
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _workers(value: int | None) -> int:
    return value or max(1, min(14, os.cpu_count() or 4))


def _json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _transient_replace_error(error: BaseException) -> bool:
    return (
        os.name == "nt"
        and isinstance(error, PermissionError)
        and getattr(error, "winerror", None) in {5, 32, 33}
    )


def _replace(source: Path, destination: Path) -> None:
    for attempt in Retrying(
        retry=retry_if_exception(_transient_replace_error),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=2),
        stop=stop_after_attempt(8),
        reraise=True,
    ):
        with attempt:
            os.replace(source, destination)


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            json.dump(
                payload,
                file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        _replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _normalize_snptee_filename(name: str) -> str:
    return re.sub(r"\s+", "_", name.strip())


def _hash_paths(
    paths: Iterable[Path],
    *,
    workers: int,
) -> dict[Path, str]:
    ordered = sorted({path.resolve() for path in paths})
    with ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="bootstrap-sha256",
    ) as executor:
        hashes = dict(zip(ordered, executor.map(file_sha256, ordered), strict=True))
    return hashes


def _source_index(
    *,
    workers: int,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    for source in SOURCE_ROOTS:
        if not source.root.is_dir():
            raise NotADirectoryError(
                f"Raiz aprovada não encontrada: {source.root}"
            )
    indexed_paths: list[tuple[int, SourceRoot, Path]] = []
    for priority, source in enumerate(SOURCE_ROOTS):
        indexed_paths.extend(
            (priority, source, path)
            for path in source.root.rglob("*.pdf")
            if path.is_file()
        )
    hashes = _hash_paths(
        (path for _, _, path in indexed_paths),
        workers=workers,
    )
    by_sha: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rename_plan: list[dict[str, Any]] = []
    for priority, source, path in indexed_paths:
        relative = path.relative_to(source.root)
        checksum = hashes[path.resolve()]
        candidate = {
            "priority": priority,
            "collection": source.collection,
            "collection_slug": source.slug,
            "root": str(source.root.resolve()),
            "path": str(path.resolve()),
            "relative_path": relative.as_posix(),
            "preserve_tree": source.preserve_tree,
            "normalize_whitespace": source.normalize_whitespace,
            "sha256": checksum,
        }
        by_sha[checksum].append(candidate)
        if source.normalize_whitespace:
            normalized_name = _normalize_snptee_filename(path.name)
            if normalized_name != path.name:
                rename_plan.append(
                    {
                        "source": str(path.resolve()),
                        "destination": str(
                            path.with_name(normalized_name).resolve()
                        ),
                        "sha256": checksum,
                    }
                )

    for candidates in by_sha.values():
        candidates.sort(
            key=lambda item: (
                int(item["priority"]),
                str(item["relative_path"]).casefold(),
                str(item["relative_path"]),
            )
        )
    _validate_source_renames(rename_plan)
    return by_sha, sorted(rename_plan, key=lambda item: str(item["source"]))


def _validate_source_renames(rename_plan: list[dict[str, Any]]) -> None:
    by_destination: dict[str, list[str]] = defaultdict(list)
    for item in rename_plan:
        source = Path(str(item["source"])).resolve()
        destination = Path(str(item["destination"])).resolve()
        root = SOURCE_ROOTS[0].root.resolve()
        if not source.is_relative_to(root) or not destination.is_relative_to(root):
            raise RuntimeError("Rename SNPTEE escapou da raiz aprovada.")
        by_destination[str(destination).casefold()].append(str(source))
        if destination.exists() and destination != source:
            raise FileExistsError(
                f"Destino SNPTEE já existe: {destination}"
            )
    collisions = {
        destination: sources
        for destination, sources in by_destination.items()
        if len(sources) > 1
    }
    if collisions:
        raise RuntimeError(
            f"Normalização SNPTEE produziria colisões: {collisions}"
        )


def _selected_source(
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    return candidates[0] if candidates else None


def _target_for(
    row: dict[str, Any],
    candidate: dict[str, Any] | None,
) -> tuple[str, str, str]:
    if candidate is None:
        collection = "Diversos"
        slug = "diversos"
        within = Path(str(row["filename"]))
    else:
        collection = str(candidate["collection"])
        slug = str(candidate["collection_slug"])
        source_relative = PurePosixPath(str(candidate["relative_path"]))
        filename = source_relative.name
        if bool(candidate["normalize_whitespace"]):
            filename = _normalize_snptee_filename(filename)
        within = (
            Path(*source_relative.parent.parts) / filename
            if bool(candidate["preserve_tree"])
            else Path(filename)
        )
    return collection, slug, within.as_posix()


def _existing_pdf(
    source: Path,
    destination: Path,
) -> Path:
    if source.is_file():
        return source
    if destination.is_file():
        return destination
    raise FileNotFoundError(
        f"PDF não existe na origem nem no destino: {source} -> {destination}"
    )


def build_plan(workers: int = 3) -> Path:
    inventory_path = settings.inventory_path
    if not inventory_path.is_file():
        raise FileNotFoundError(inventory_path)
    inventory = pd.read_csv(inventory_path)
    required = {
        "sha256",
        "relative_path",
        "filename",
        "status",
        "error",
    }
    missing = sorted(required - set(inventory.columns))
    if missing:
        raise ValueError(f"Inventário atual sem colunas: {missing}")
    expected_valid_total = sum(EXPECTED_VALID_COUNTS.values())
    promoted_state = (
        len(inventory) == expected_valid_total
        and inventory["status"].eq("ok").all()
    )
    if not promoted_state and len(inventory) != (
        expected_valid_total + EXPECTED_INVALID_COUNT
    ):
        raise RuntimeError(
            "Bootstrap espera o inventário inicial com 4.048 linhas ou o "
            f"estado promovido com 4.040; recebeu {len(inventory)}."
        )
    invalid = inventory[inventory["status"].ne("ok")].copy()
    valid = inventory[inventory["status"].eq("ok")].copy()
    expected_invalid = 0 if promoted_state else EXPECTED_INVALID_COUNT
    if len(invalid) != expected_invalid:
        raise RuntimeError(
            f"Esperados {expected_invalid} inválidos; encontrados {len(invalid)}."
        )

    if promoted_state:
        promoted_columns = {
            "collection",
            "collection_slug",
            "collection_relative_path",
            "document_id",
            "revision_id",
        }
        missing_promoted = sorted(promoted_columns - set(inventory.columns))
        if missing_promoted:
            raise ValueError(
                f"Inventário promovido sem colunas: {missing_promoted}"
            )
        source_by_sha: dict[str, list[dict[str, Any]]] = {}
        source_renames: list[dict[str, Any]] = []
    else:
        source_by_sha, source_renames = _source_index(
            workers=_workers(workers),
        )
    records: list[dict[str, Any]] = []
    target_keys: dict[str, str] = {}
    artifact_keys: dict[str, str] = {}
    counts: Counter[str] = Counter()
    corpus_paths: list[Path] = []
    for row_value in valid.to_dict(orient="records"):
        row = {key: _json_value(value) for key, value in row_value.items()}
        sha256 = str(row["sha256"]).casefold()
        if promoted_state:
            candidate = None
            collection = str(row["collection"])
            slug = str(row["collection_slug"])
            within = PurePosixPath(
                str(row["collection_relative_path"]).replace("\\", "/")
            ).as_posix()
            target_relative = Path(str(row["relative_path"]))
            expected_relative = (
                Path(collection) / Path(*PurePosixPath(within).parts)
            )
            if target_relative != expected_relative:
                raise ValueError(
                    "Layout promovido divergiu de coleção + path relativo: "
                    f"{target_relative} != {expected_relative}"
                )
            old_relative = target_relative
        else:
            candidate = _selected_source(source_by_sha.get(sha256, []))
            collection, slug, within = _target_for(row, candidate)
            target_relative = (
                Path(collection) / Path(*PurePosixPath(within).parts)
            )
            old_relative = Path(str(row["relative_path"]))
        source_pdf = settings.document_store_dir / old_relative
        target_pdf = settings.document_store_dir / target_relative
        actual_pdf = _existing_pdf(source_pdf, target_pdf)
        actual_sha = file_sha256(actual_pdf)
        if actual_sha != sha256:
            raise ValueError(
                f"PDF divergiu do inventário: {actual_pdf} ({actual_sha} != {sha256})"
            )
        key = target_relative.as_posix().casefold()
        sibling_key = target_relative.with_suffix("").as_posix().casefold()
        if key in target_keys:
            raise RuntimeError(
                f"Colisão de destino: {target_relative} e {target_keys[key]}"
            )
        if sibling_key in artifact_keys:
            raise RuntimeError(
                "Colisão de diretório irmão: "
                f"{target_relative.with_suffix('')} e {artifact_keys[sibling_key]}"
            )
        target_keys[key] = old_relative.as_posix()
        artifact_keys[sibling_key] = old_relative.as_posix()
        catalog_id = document_uuid(slug, within)
        revision_id = revision_uuid(catalog_id, sha256)
        if promoted_state and (
            str(row["document_id"]) != str(catalog_id)
            or str(row["revision_id"]) != str(revision_id)
        ):
            raise ValueError(
                f"Identidade promovida divergiu para {target_relative}."
            )
        records.append(
            {
                "old_relative_path": old_relative.as_posix(),
                "target_relative_path": target_relative.as_posix(),
                "collection_relative_path": within,
                "collection": collection,
                "collection_slug": slug,
                "collection_id": str(collection_uuid(slug)),
                "document_id": str(catalog_id),
                "revision_id": str(revision_id),
                "sha256": sha256,
                "selected_source": candidate,
            }
        )
        counts[slug] += 1
        corpus_paths.append(actual_pdf)

    if dict(counts) != EXPECTED_VALID_COUNTS:
        raise RuntimeError(
            "Classificação divergiu do estado inicial aprovado: "
            f"{dict(counts)} != {EXPECTED_VALID_COUNTS}"
        )

    invalid_records: list[dict[str, Any]] = []
    for row_value in invalid.to_dict(orient="records"):
        row = {key: _json_value(value) for key, value in row_value.items()}
        relative = Path(str(row["relative_path"]))
        pdf = settings.document_store_dir / relative
        if not pdf.is_file():
            raise FileNotFoundError(pdf)
        sha256 = str(row["sha256"]).casefold()
        if file_sha256(pdf) != sha256:
            raise ValueError(f"PDF inválido divergiu do inventário: {pdf}")
        invalid_records.append(
            {
                "relative_path": relative.as_posix(),
                "sha256": sha256,
                "error": row.get("error"),
            }
        )

    bootstrap_dir = settings.data_dir / "bootstrap"
    bootstrap_dir.mkdir(parents=True, exist_ok=True)
    if promoted_state:
        plan_inventory = bootstrap_dir / "promoted-validation-inventory.csv"
        shutil.copy2(inventory_path, plan_inventory)
    else:
        plan_inventory = bootstrap_dir / "promoted-source-inventory.csv"
        if not plan_inventory.exists():
            shutil.copy2(inventory_path, plan_inventory)
    plan_body = {
        "schema_version": PLAN_VERSION,
        "source_state": "promoted" if promoted_state else "legacy",
        "catalog_namespace": str(CATALOG_NAMESPACE),
        "created_at": _now(),
        "documents_root": str(settings.document_store_dir.resolve()),
        "inventory_path": str(plan_inventory.resolve()),
        "expected_counts": dict(counts),
        "documents": sorted(
            records,
            key=lambda item: str(item["target_relative_path"]).casefold(),
        ),
        "invalid_documents": invalid_records,
        "source_renames": source_renames,
    }
    plan_body["plan_sha256"] = canonical_json_sha256(plan_body)
    output = bootstrap_dir / (
        "bootstrap-validation-plan.json"
        if promoted_state
        else "bootstrap-plan.json"
    )
    _atomic_json(output, plan_body)
    print(
        f"Plano: {output} | válidos={len(records)} | "
        f"inválidos={len(invalid_records)} | "
        f"renomes_snptee={len(source_renames)}"
    )
    return output


def _load_plan(path: Path | None = None) -> dict[str, Any]:
    plan_path = path or settings.data_dir / "bootstrap" / "bootstrap-plan.json"
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != PLAN_VERSION:
        raise ValueError(f"Plano de bootstrap inválido: {plan_path}")
    declared = str(payload.get("plan_sha256", ""))
    body = {key: value for key, value in payload.items() if key != "plan_sha256"}
    if canonical_json_sha256(body) != declared:
        raise ValueError(f"Checksum do plano divergiu: {plan_path}")
    if Path(str(payload["documents_root"])).resolve() != (
        settings.document_store_dir.resolve()
    ):
        raise ValueError("Plano pertence a outro document store.")
    return payload


def _apply_source_renames(plan: dict[str, Any]) -> int:
    applied = 0
    root = SOURCE_ROOTS[0].root.resolve()
    for item in plan["source_renames"]:
        source = Path(str(item["source"])).resolve()
        destination = Path(str(item["destination"])).resolve()
        expected_sha = str(item["sha256"])
        if not source.is_relative_to(root) or not destination.is_relative_to(root):
            raise RuntimeError("Rename SNPTEE fora da raiz aprovada.")
        if source.is_file():
            if file_sha256(source) != expected_sha:
                raise ValueError(
                    f"SHA divergiu antes do rename SNPTEE: {source}"
                )
            if destination.exists():
                raise FileExistsError(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _replace(source, destination)
            applied += 1
        elif not destination.is_file():
            raise FileNotFoundError(
                f"Rename SNPTEE não pode ser retomado: {source} -> {destination}"
            )
        if file_sha256(destination) != expected_sha:
            raise ValueError(f"SHA divergiu após rename SNPTEE: {destination}")
    return applied


def _quarantine_invalid(plan: dict[str, Any]) -> int:
    root = settings.document_store_dir.resolve()
    quarantine = (
        settings.data_dir / "bootstrap" / "quarantine-invalid"
    ).resolve()
    if not quarantine.is_relative_to(settings.data_dir.resolve()):
        raise RuntimeError("Quarentena inválida.")
    moved = 0
    for item in plan["invalid_documents"]:
        relative = Path(str(item["relative_path"]))
        source_pdf = (root / relative).resolve()
        source_dir = source_pdf.parent / source_pdf.stem.rstrip(" .")
        destination_root = quarantine / str(item["sha256"])
        destination_pdf = destination_root / source_pdf.name
        destination_dir = destination_root / source_dir.name
        if not source_pdf.is_relative_to(root) or not source_dir.is_relative_to(root):
            raise RuntimeError("Inválido fora do document store.")
        destination_root.mkdir(parents=True, exist_ok=True)
        if source_pdf.is_file():
            if file_sha256(source_pdf) != str(item["sha256"]):
                raise ValueError(
                    f"SHA divergiu antes da quarentena: {source_pdf}"
                )
            if destination_pdf.exists():
                raise FileExistsError(destination_pdf)
            _replace(source_pdf, destination_pdf)
            moved += 1
        elif not destination_pdf.is_file():
            raise FileNotFoundError(source_pdf)
        if file_sha256(destination_pdf) != str(item["sha256"]):
            raise ValueError(
                f"SHA divergiu na quarentena: {destination_pdf}"
            )
        if source_dir.is_dir():
            if destination_dir.exists():
                raise FileExistsError(destination_dir)
            _replace(source_dir, destination_dir)
        elif not destination_dir.exists():
            destination_dir.mkdir()
    return moved


def _rearrange_staged_document(
    stage: Path,
    *,
    document_id: str,
) -> None:
    intermediate = stage / "intermediate"
    canonical = stage / "canonical"
    intermediate.mkdir(exist_ok=True)
    canonical.mkdir(exist_ok=True)
    legacy_mineru = stage / "mineru"
    mineru = intermediate / "mineru"
    if legacy_mineru.is_dir():
        if mineru.exists():
            raise FileExistsError(mineru)
        _replace(legacy_mineru, mineru)
    elif not mineru.is_dir():
        raise FileNotFoundError(
            f"Documento extraído sem diretório MinerU: {stage}"
        )
    for name in CANONICAL_FILES:
        legacy = stage / name
        target = canonical / name
        if legacy.is_file():
            if target.exists():
                raise FileExistsError(target)
            _replace(legacy, target)
        elif not target.is_file():
            raise FileNotFoundError(
                f"Artefato canônico ausente durante bootstrap: {legacy}"
            )
    operational_quarantine = (
        settings.data_dir
        / "bootstrap"
        / "quarantine-operational"
        / document_id
    )
    for path in tuple(stage.iterdir()):
        if (
            path.is_file()
            and path.name.startswith(".")
            and path.name.casefold().endswith(".tmp")
        ):
            operational_quarantine.mkdir(parents=True, exist_ok=True)
            destination = operational_quarantine / path.name
            if destination.exists():
                raise FileExistsError(destination)
            _replace(path, destination)
    unexpected = [
        path.name
        for path in stage.iterdir()
        if path.name not in {"intermediate", "canonical", "manifest.json"}
    ]
    if unexpected:
        raise RuntimeError(
            f"Arquivos legados inesperados em {stage}: {unexpected}"
        )


def _migrate_one(record: dict[str, Any]) -> None:
    root = settings.document_store_dir.resolve()
    source_pdf = (root / str(record["old_relative_path"])).resolve()
    target_pdf = (root / str(record["target_relative_path"])).resolve()
    if not source_pdf.is_relative_to(root) or not target_pdf.is_relative_to(root):
        raise RuntimeError("Migração escapou do document store.")
    source_dir = source_pdf.parent / source_pdf.stem.rstrip(" .")
    target_dir = target_pdf.parent / target_pdf.stem.rstrip(" .")
    stage_pdf = target_pdf.with_name(
        f".{target_pdf.name}.{record['document_id']}.bootstrap"
    )
    stage_dir = target_dir.with_name(
        f".{target_dir.name}.{record['document_id']}.bootstrap"
    )
    target_pdf.parent.mkdir(parents=True, exist_ok=True)

    current_pdfs = {
        path.resolve()
        for path in (source_pdf, stage_pdf, target_pdf)
        if path.is_file()
    }
    if len(current_pdfs) != 1:
        raise RuntimeError(
            "Migração exige exatamente uma cópia física do PDF: "
            f"{sorted(str(path) for path in current_pdfs)}"
        )
    current_pdf = next(iter(current_pdfs))
    if file_sha256(current_pdf) != str(record["sha256"]):
        raise ValueError(f"SHA divergiu antes da migração: {current_pdf}")

    if not target_dir.is_dir():
        if not stage_dir.is_dir():
            if not source_dir.is_dir():
                raise FileNotFoundError(source_dir)
            _replace(source_dir, stage_dir)
        _rearrange_staged_document(
            stage_dir,
            document_id=str(record["document_id"]),
        )

    if not target_pdf.is_file():
        if not stage_pdf.is_file():
            if not source_pdf.is_file():
                raise FileNotFoundError(source_pdf)
            _replace(source_pdf, stage_pdf)
        if file_sha256(stage_pdf) != str(record["sha256"]):
            raise ValueError(f"SHA divergiu no staging: {stage_pdf}")

    if not target_dir.is_dir():
        _replace(stage_dir, target_dir)
    if not target_pdf.is_file():
        _replace(stage_pdf, target_pdf)
    if file_sha256(target_pdf) != str(record["sha256"]):
        raise ValueError(f"SHA divergiu no destino: {target_pdf}")


def _preflight_apply(
    plan: dict[str, Any],
    *,
    workers: int,
) -> dict[str, int]:
    expected: dict[Path, tuple[str, str]] = {}

    def require_one(
        candidates: Iterable[Path],
        *,
        sha256: str,
        label: str,
    ) -> None:
        existing = {
            candidate.resolve()
            for candidate in candidates
            if candidate.is_file()
        }
        if len(existing) != 1:
            raise RuntimeError(
                f"{label}: esperada exatamente uma cópia física; "
                f"encontradas={sorted(str(path) for path in existing)}"
            )
        path = next(iter(existing))
        previous = expected.get(path)
        contract = (sha256, label)
        if previous is not None and previous[0] != sha256:
            raise RuntimeError(
                f"Contratos SHA conflitantes para {path}: {previous} e {contract}"
            )
        expected[path] = contract

    snptee_root = SOURCE_ROOTS[0].root.resolve()
    for item in plan["source_renames"]:
        source = Path(str(item["source"])).resolve()
        destination = Path(str(item["destination"])).resolve()
        if (
            not source.is_relative_to(snptee_root)
            or not destination.is_relative_to(snptee_root)
        ):
            raise RuntimeError("Preflight encontrou rename SNPTEE fora da raiz.")
        require_one(
            (source, destination),
            sha256=str(item["sha256"]),
            label=f"rename SNPTEE {source}",
        )

    documents_root = settings.document_store_dir.resolve()
    quarantine = (
        settings.data_dir / "bootstrap" / "quarantine-invalid"
    ).resolve()
    for item in plan["invalid_documents"]:
        source = (documents_root / str(item["relative_path"])).resolve()
        destination = quarantine / str(item["sha256"]) / source.name
        require_one(
            (source, destination),
            sha256=str(item["sha256"]),
            label=f"documento inválido {source}",
        )

    for record in plan["documents"]:
        source = (
            documents_root / str(record["old_relative_path"])
        ).resolve()
        target = (
            documents_root / str(record["target_relative_path"])
        ).resolve()
        stage = target.with_name(
            f".{target.name}.{record['document_id']}.bootstrap"
        )
        require_one(
            (source, stage, target),
            sha256=str(record["sha256"]),
            label=f"documento {record['old_relative_path']}",
        )
        source_dir = source.parent / source.stem.rstrip(" .")
        target_dir = target.parent / target.stem.rstrip(" .")
        stage_dir = target_dir.with_name(
            f".{target_dir.name}.{record['document_id']}.bootstrap"
        )
        current_dirs = {
            path.resolve()
            for path in (source_dir, stage_dir, target_dir)
            if path.is_dir()
        }
        if len(current_dirs) != 1:
            raise RuntimeError(
                "Documento exige exatamente um diretório de artefatos: "
                f"{record['old_relative_path']} -> "
                f"{sorted(str(path) for path in current_dirs)}"
            )

    hashes = _hash_paths(expected, workers=_workers(workers))
    for path, actual in hashes.items():
        declared, label = expected[path]
        if actual != declared:
            raise ValueError(
                f"{label}: SHA mudou desde o plano ({actual} != {declared})."
            )
    return {
        "verified_files": len(expected),
        "documents": len(plan["documents"]),
        "source_renames": len(plan["source_renames"]),
        "invalid_documents": len(plan["invalid_documents"]),
    }


def _promoted_inventory(
    plan: dict[str, Any],
) -> pd.DataFrame:
    legacy = pd.read_csv(Path(str(plan["inventory_path"])))
    by_relative = {
        str(row["relative_path"]): row
        for row in legacy.to_dict(orient="records")
    }
    rows: list[dict[str, Any]] = []
    for record in plan["documents"]:
        old_relative = str(record["old_relative_path"]).replace("/", os.sep)
        row = by_relative.get(old_relative)
        if row is None:
            row = by_relative.get(str(record["old_relative_path"]))
        if row is None:
            raise KeyError(
                f"Documento do plano ausente no inventário: {old_relative}"
            )
        relative = Path(str(record["target_relative_path"]))
        within = Path(str(record["collection_relative_path"]))
        absolute = settings.document_store_dir / relative
        promoted = {
            key: _json_value(value)
            for key, value in row.items()
        }
        promoted.update(
            {
                "collection": record["collection"],
                "collection_slug": record["collection_slug"],
                "document_id": record["document_id"],
                "revision_id": record["revision_id"],
                "path": str(absolute.resolve()),
                "relative_path": str(relative),
                "collection_relative_path": str(within),
                "filename": absolute.name,
                "stem": absolute.stem,
                "artifact_dir": str(
                    (absolute.parent / absolute.stem.rstrip(" .")).resolve()
                ),
                "manifest_path": str(
                    (
                        absolute.parent
                        / absolute.stem.rstrip(" .")
                        / "manifest.json"
                    ).resolve()
                ),
                "status": "ok",
                "error": None,
            }
        )
        rows.append(promoted)
    return (
        pd.DataFrame(rows)
        .reindex(columns=INVENTORY_COLUMNS)
        .sort_values(["collection", "relative_path"])
        .reset_index(drop=True)
    )


def _write_inventory(frame: pd.DataFrame) -> None:
    output = settings.inventory_path
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.bootstrap.tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    _replace(temporary, output)
    errors = output.with_name("inventory_errors.csv")
    temporary_errors = errors.with_name(f".{errors.name}.bootstrap.tmp")
    frame.iloc[0:0].to_csv(
        temporary_errors,
        index=False,
        encoding="utf-8-sig",
    )
    _replace(temporary_errors, errors)


def refresh_manifests(workers: int = 3) -> dict[str, int]:
    inventory = pd.read_csv(settings.inventory_path)
    required = {
        "collection",
        "collection_slug",
        "document_id",
        "revision_id",
        "sha256",
        "relative_path",
        "collection_relative_path",
    }
    missing = sorted(required - set(inventory.columns))
    if missing:
        raise ValueError(f"Inventário promovido sem colunas: {missing}")
    rows = inventory[inventory["status"].eq("ok")].to_dict(orient="records")

    def refresh(row: dict[str, Any]) -> Path:
        layout = document_layout(row)
        try:
            existing = json.loads(
                layout.manifest_path.read_text(encoding="utf-8")
            )
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            existing = None
        return write_document_manifest(
            row,
            origin="bootstrap",
            existing_manifest=(
                existing if isinstance(existing, dict) else None
            ),
        )

    with ThreadPoolExecutor(
        max_workers=_workers(workers),
        thread_name_prefix="bootstrap-manifest",
    ) as executor:
        paths = list(executor.map(refresh, rows))
    return {"documents": len(paths), "manifests": len(paths)}


def apply_plan(workers: int = 3) -> dict[str, Any]:
    plan = _load_plan()
    state_path = settings.data_dir / "bootstrap" / "bootstrap-state.json"
    if str(plan.get("source_state") or "legacy") != "legacy":
        raise RuntimeError(
            "O plano descreve um inventário já promovido; nada deve ser "
            "aplicado. Use `poe bootstrap plan` apenas para validação."
        )
    try:
        previous_state = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        previous_state = None
    if (
        isinstance(previous_state, dict)
        and previous_state.get("status") == "completed"
    ):
        previous_hash = str(previous_state.get("plan_sha256") or "")
        if previous_hash == str(plan["plan_sha256"]):
            raise RuntimeError(
                "Este bootstrap já foi aplicado e validado; a reaplicação "
                "foi bloqueada para preservar inventário e manifests."
            )
        raise RuntimeError(
            "Já existe outro bootstrap concluído. Crie uma migração "
            "explícita em vez de reaplicar um plano legado."
        )
    preflight = _preflight_apply(plan, workers=workers)
    state: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "phase": "source-renames",
        "plan_sha256": plan["plan_sha256"],
        "started_at": _now(),
        "preflight": preflight,
        "migrated_documents": 0,
    }
    _atomic_json(state_path, state)
    renamed = _apply_source_renames(plan)
    state.update(
        phase="quarantine-invalid",
        source_renames_total=len(plan["source_renames"]),
        source_renames_applied_this_run=renamed,
    )
    _atomic_json(state_path, state)
    quarantined = _quarantine_invalid(plan)
    state.update(
        phase="documents",
        invalid_documents_total=len(plan["invalid_documents"]),
        invalid_documents_quarantined_this_run=quarantined,
    )
    _atomic_json(state_path, state)
    for index, record in enumerate(plan["documents"], start=1):
        _migrate_one(record)
        if index % 100 == 0 or index == len(plan["documents"]):
            state["migrated_documents"] = index
            _atomic_json(state_path, state)
            print(f"Migrados: {index}/{len(plan['documents'])}", flush=True)
    state["phase"] = "inventory"
    _atomic_json(state_path, state)
    promoted = _promoted_inventory(plan)
    _write_inventory(promoted)
    state["phase"] = "manifests"
    _atomic_json(state_path, state)
    manifests = refresh_manifests(workers)
    report = {
        "schema_version": 1,
        "applied_at": _now(),
        "plan_sha256": plan["plan_sha256"],
        "source_renames_total": len(plan["source_renames"]),
        "source_renames_applied_this_run": renamed,
        "invalid_documents_quarantined": len(
            plan["invalid_documents"]
        ),
        "invalid_documents_quarantined_this_run": quarantined,
        "operational_files_quarantined": sum(
            1
            for path in (
                settings.data_dir
                / "bootstrap"
                / "quarantine-operational"
            ).rglob("*")
            if path.is_file()
        ),
        "document_count": len(promoted),
        "collection_counts": (
            promoted.groupby("collection_slug").size().sort_index().to_dict()
        ),
        "manifest_count": manifests["manifests"],
        "inventory_path": str(settings.inventory_path.resolve()),
        "preflight": preflight,
    }
    output = settings.data_dir / "bootstrap" / "bootstrap-report.json"
    _atomic_json(output, report)
    state.update(
        status="completed",
        phase="completed",
        source_renames_total=len(plan["source_renames"]),
        invalid_documents_total=len(plan["invalid_documents"]),
        completed_at=_now(),
        report_path=str(output.resolve()),
    )
    _atomic_json(state_path, state)
    print(f"Bootstrap aplicado: {output}")
    return report


def bootstrap(
    action: str = "plan",
    workers: int = 3,
) -> Path | dict[str, Any] | dict[str, int]:
    lock_path = settings.data_dir / "bootstrap" / "bootstrap.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(lock_path, timeout=0):
            if action == "plan":
                return build_plan(workers)
            if action == "apply":
                return apply_plan(workers)
            if action == "refresh-manifests":
                return refresh_manifests(workers)
            raise ValueError(
                "Ação inválida. Use plan, apply ou refresh-manifests."
            )
    except Timeout as error:
        raise RuntimeError(
            f"Outro bootstrap está em execução: {lock_path}"
        ) from error
