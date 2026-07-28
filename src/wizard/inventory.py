from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from pypdf import PdfReader


INVENTORY_COLUMNS = [
    "document_id",
    "sha256",
    "path",
    "relative_path",
    "filename",
    "stem",
    "extension",
    "size_bytes",
    "size_mb",
    "created_at",
    "modified_at",
    "page_count",
    "encrypted",
    "pdf_version",
    "title",
    "author",
    "subject",
    "creator",
    "producer",
    "status",
    "error",
]


def _utc_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _safe_metadata_value(metadata: Any, key: str) -> str | None:
    if metadata is None:
        return None

    value = getattr(metadata, key, None)

    if value is None and isinstance(metadata, dict):
        value = metadata.get(key)

    if value is None:
        return None

    value = str(value).strip()
    return value or None


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)

    return digest.hexdigest()


def iter_documents(
    corpus_dir: Path,
    *,
    recursive: bool = True,
    include_extensions: Iterable[str] = (".pdf",),
) -> list[Path]:
    corpus_dir = corpus_dir.expanduser().resolve()

    if not corpus_dir.exists():
        raise FileNotFoundError(f"Diretório não encontrado: {corpus_dir}")

    if not corpus_dir.is_dir():
        raise NotADirectoryError(f"Não é um diretório: {corpus_dir}")

    extensions = {
        extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        for extension in include_extensions
    }

    iterator = corpus_dir.rglob("*") if recursive else corpus_dir.glob("*")

    return sorted(
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() in extensions
    )


def inspect_pdf(
    path: Path,
    *,
    corpus_dir: Path,
    hash_chunk_size: int = 1024 * 1024,
) -> dict[str, Any]:
    resolved_path = path.resolve()
    stat = resolved_path.stat()

    row: dict[str, Any] = {
        "document_id": None,
        "sha256": None,
        "path": str(resolved_path),
        "relative_path": str(resolved_path.relative_to(corpus_dir)),
        "filename": resolved_path.name,
        "stem": resolved_path.stem,
        "extension": resolved_path.suffix.lower(),
        "size_bytes": int(stat.st_size),
        "size_mb": round(stat.st_size / (1024 * 1024), 4),
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
        file_hash = sha256_file(resolved_path, chunk_size=hash_chunk_size)
        row["sha256"] = file_hash
        row["document_id"] = file_hash[:16]

        reader = PdfReader(str(resolved_path), strict=False)
        row["encrypted"] = bool(reader.is_encrypted)

        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                pass

        try:
            row["page_count"] = len(reader.pages)
        except Exception:
            row["page_count"] = None

        header = getattr(reader, "pdf_header", None)
        if header:
            row["pdf_version"] = str(header).replace("%PDF-", "").strip()

        metadata = reader.metadata
        row["title"] = _safe_metadata_value(metadata, "title")
        row["author"] = _safe_metadata_value(metadata, "author")
        row["subject"] = _safe_metadata_value(metadata, "subject")
        row["creator"] = _safe_metadata_value(metadata, "creator")
        row["producer"] = _safe_metadata_value(metadata, "producer")

    except Exception as error:
        row["status"] = "error"
        row["error"] = f"{type(error).__name__}: {error}"

    return row


def build_inventory(
    corpus_dir: Path,
    *,
    recursive: bool = True,
    workers: int | None = None,
    hash_chunk_size: int = 1024 * 1024,
    include_extensions: Iterable[str] = (".pdf",),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    corpus_dir = corpus_dir.expanduser().resolve()

    paths = iter_documents(
        corpus_dir,
        recursive=recursive,
        include_extensions=include_extensions,
    )

    resolved_workers = workers or max(1, min(8, os.cpu_count() or 4))
    rows: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=resolved_workers) as executor:
        futures = {
            executor.submit(
                inspect_pdf,
                path,
                corpus_dir=corpus_dir,
                hash_chunk_size=hash_chunk_size,
            ): path
            for path in paths
        }

        for index, future in enumerate(as_completed(futures), start=1):
            path = futures[future]

            try:
                rows.append(future.result())
            except Exception as error:
                rows.append(
                    {
                        "path": str(path.resolve()),
                        "relative_path": str(path.resolve().relative_to(corpus_dir)),
                        "filename": path.name,
                        "stem": path.stem,
                        "extension": path.suffix.lower(),
                        "status": "error",
                        "error": f"{type(error).__name__}: {error}",
                    }
                )

            if index % 100 == 0 or index == len(paths):
                print(f"Processados: {index}/{len(paths)}")

    inventory = (
        pd.DataFrame(rows)
        .reindex(columns=INVENTORY_COLUMNS)
        .sort_values(["relative_path", "filename"])
        .reset_index(drop=True)
    )

    errors = inventory.loc[
        inventory["status"].ne("ok"),
        ["path", "relative_path", "filename", "error"],
    ].reset_index(drop=True)

    return inventory, errors


def duplicate_groups(inventory: pd.DataFrame) -> pd.DataFrame:
    valid = inventory[inventory["sha256"].notna()].copy()

    duplicate_hashes = (
        valid.groupby("sha256")
        .size()
        .loc[lambda series: series > 1]
        .index
    )

    return (
        valid[valid["sha256"].isin(duplicate_hashes)]
        .sort_values(["sha256", "relative_path"])
        .reset_index(drop=True)
    )


def inventory_summary(inventory: pd.DataFrame) -> pd.Series:
    pages = pd.to_numeric(inventory["page_count"], errors="coerce")
    duplicates = duplicate_groups(inventory)

    return pd.Series(
        {
            "documents_total": int(len(inventory)),
            "documents_ok": int(inventory["status"].eq("ok").sum()),
            "documents_error": int(inventory["status"].ne("ok").sum()),
            "encrypted": int(inventory["encrypted"].fillna(False).sum()),
            "size_total_gb": round(
                pd.to_numeric(inventory["size_bytes"], errors="coerce").sum()
                / (1024**3),
                4,
            ),
            "size_median_mb": round(
                pd.to_numeric(inventory["size_mb"], errors="coerce").median(),
                4,
            ),
            "pages_total": int(pages.sum()) if pages.notna().any() else 0,
            "pages_median": float(pages.median()) if pages.notna().any() else None,
            "duplicate_files": int(len(duplicates)),
            "duplicate_groups": int(duplicates["sha256"].nunique()),
        }
    )


def save_inventory(
    inventory: pd.DataFrame,
    errors: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "inventory_parquet": output_dir / "inventory.parquet",
        "inventory_csv": output_dir / "inventory.csv",
        "errors_csv": output_dir / "inventory_errors.csv",
        "duplicates_csv": output_dir / "inventory_duplicates.csv",
        "summary_json": output_dir / "inventory_summary.json",
    }

    inventory.to_parquet(paths["inventory_parquet"], index=False)
    inventory.to_csv(paths["inventory_csv"], index=False, encoding="utf-8-sig")
    errors.to_csv(paths["errors_csv"], index=False, encoding="utf-8-sig")
    duplicate_groups(inventory).to_csv(
        paths["duplicates_csv"],
        index=False,
        encoding="utf-8-sig",
    )
    inventory_summary(inventory).to_json(
        paths["summary_json"],
        force_ascii=False,
        indent=2,
    )

    return paths
