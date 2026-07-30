from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pypdf import PdfReader

from .identity import collection_slug, document_uuid, revision_uuid
from .layout import document_layout
from .settings import settings

INVENTORY_COLUMNS = [
    "collection", "collection_slug", "document_id", "revision_id",
    "sha256", "path", "relative_path", "collection_relative_path",
    "filename", "stem",
    "artifact_dir", "manifest_path",
    "extension", "size_bytes", "size_mb", "created_at", "modified_at",
    "page_count", "encrypted", "pdf_version", "title", "author", "subject",
    "creator", "producer", "status", "error",
]


def _utc_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _metadata(metadata: Any, key: str) -> str | None:
    value = getattr(metadata, key, None) if metadata is not None else None
    if value is None and isinstance(metadata, dict):
        value = metadata.get(key)
    text = str(value).strip() if value is not None else ""
    return text or None


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_pdf(
    path: Path,
    documents_dir: Path,
    *,
    collection: str | None = None,
    logical_prefix: str = "",
) -> dict[str, Any]:
    path = path.resolve()
    documents_dir = documents_dir.resolve()
    stat = path.stat()
    source_relative_path = path.relative_to(documents_dir)
    if collection is None:
        if len(source_relative_path.parts) < 2:
            raise ValueError(
                "Cada PDF canônico deve ficar dentro do diretório de sua "
                f"coleção: {source_relative_path}"
            )
        collection_name = source_relative_path.parts[0]
        collection_relative_path = Path(*source_relative_path.parts[1:])
    else:
        collection_name = collection.strip()
        prefix = Path(logical_prefix.replace("\\", "/"))
        if prefix.is_absolute() or ".." in prefix.parts:
            raise ValueError(
                f"Prefixo lógico inválido: {logical_prefix!r}"
            )
        collection_relative_path = prefix / source_relative_path
        if (
            not collection_name
            or collection_relative_path.is_absolute()
            or ".." in collection_relative_path.parts
        ):
            raise ValueError("Coleção ou path lógico inválido.")
    relative_path = Path(collection_name) / collection_relative_path
    slug = collection_slug(collection_name)
    row: dict[str, Any] = {
        "collection": collection_name,
        "collection_slug": slug,
        "document_id": None,
        "revision_id": None,
        "sha256": None,
        "path": str(path),
        "relative_path": str(relative_path),
        "collection_relative_path": str(collection_relative_path),
        "filename": path.name,
        "stem": path.stem,
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "size_mb": round(stat.st_size / 1024 / 1024, 4),
        "created_at": _utc_iso(stat.st_ctime),
        "modified_at": _utc_iso(stat.st_mtime),
        "page_count": None,
        "encrypted": None,
        "pdf_version": None,
        "title": None,
        "author": None,
        "subject": None,
        "creator": None,
        "producer": None,
        "status": "ok",
        "error": None,
    }
    try:
        sha256 = _sha256(path)
        row["sha256"] = sha256
        document_id = document_uuid(slug, collection_relative_path.as_posix())
        row["document_id"] = str(document_id)
        row["revision_id"] = str(revision_uuid(document_id, sha256))
        layout = document_layout(row)
        row["artifact_dir"] = str(layout.document_dir)
        row["manifest_path"] = str(layout.manifest_path)
        if (
            layout.document_dir.is_dir()
            and not layout.manifest_path.is_file()
            and any(layout.document_dir.iterdir())
        ):
            raise FileExistsError(
                "O diretório reservado aos artefatos já existe e não contém "
                f"manifest.json: {layout.document_dir}"
            )
        reader = PdfReader(str(path), strict=False)
        row["encrypted"] = bool(reader.is_encrypted)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                pass
        try:
            row["page_count"] = len(reader.pages)
        except Exception:
            pass
        header = getattr(reader, "pdf_header", None)
        if header:
            row["pdf_version"] = str(header).replace("%PDF-", "").strip()
        metadata = reader.metadata
        for key in ("title", "author", "subject", "creator", "producer"):
            row[key] = _metadata(metadata, key)
    except Exception as error:
        row["status"] = "error"
        row["error"] = f"{type(error).__name__}: {error}"
    return row


def build_inventory(workers: int | None = 3, recursive: bool = True) -> Path:
    """Recria o inventário a partir dos PDFs no repositório canônico."""
    documents = settings.document_store_dir
    output_path = settings.inventory_path
    if not documents.is_dir():
        raise NotADirectoryError(
            f"Repositório de documentos inválido: {documents}"
        )

    iterator = (
        documents.rglob("*.pdf") if recursive else documents.glob("*.pdf")
    )
    paths = sorted(
        path
        for path in iterator
        if path.is_file()
        and not any(
            (parent / "manifest.json").is_file()
            for parent in path.parents
            if parent != documents and documents in parent.parents
        )
    )
    resolved_workers = workers or max(1, min(14, os.cpu_count() or 4))
    rows: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=resolved_workers) as executor:
        futures = {
            executor.submit(inspect_pdf, path, documents): path
            for path in paths
        }
        for index, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if index % 100 == 0 or index == len(paths):
                print(f"Inventariados: {index}/{len(paths)}")

    inventory = pd.DataFrame(rows).reindex(columns=INVENTORY_COLUMNS)
    if not inventory.empty:
        inventory = inventory.sort_values(["relative_path", "filename"]).reset_index(drop=True)
        identities = inventory[
            inventory["document_id"].notna()
            & inventory["document_id"].duplicated(keep=False)
        ]
        if not identities.empty:
            paths_by_id = identities.groupby("document_id")["path"].apply(list)
            raise RuntimeError(
                "Mais de um path produziu a mesma identidade de catálogo: "
                f"{paths_by_id.to_dict()}"
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(output_path, index=False, encoding="utf-8-sig")
    inventory[inventory["status"].ne("ok")].to_csv(
        output_path.with_name("inventory_errors.csv"), index=False, encoding="utf-8-sig"
    )
    print(f"Manifesto: {output_path}")
    return output_path


def sample_inventory(
    size: int = 100,
    seed: int = 42,
    inventory_path: str | Path | None = None,
    sample_path: str | Path | None = None,
) -> Path:
    """Gera uma amostra reprodutível do manifesto canônico."""
    source = (
        Path(inventory_path).expanduser().resolve()
        if inventory_path
        else settings.inventory_path
    )
    output = (
        Path(sample_path).expanduser().resolve()
        if sample_path
        else settings.sample_path
    )
    inventory = pd.read_csv(source)
    valid = inventory[inventory["status"].eq("ok")].copy()
    if valid.empty:
        raise RuntimeError("Não há documentos válidos para amostrar.")
    sample_size = min(size, len(valid))
    sample = valid.sample(n=sample_size, random_state=seed).sort_values("relative_path")
    output.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"Amostra: {output} ({len(sample)} documentos)")
    return output
