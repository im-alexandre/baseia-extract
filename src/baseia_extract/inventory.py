from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pypdf import PdfReader

from .settings import settings

INVENTORY_COLUMNS = [
    "document_id", "sha256", "path", "relative_path", "filename", "stem",
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


def inspect_pdf(path: Path, corpus_dir: Path) -> dict[str, Any]:
    path = path.resolve()
    stat = path.stat()
    row: dict[str, Any] = {
        "document_id": None,
        "sha256": None,
        "path": str(path),
        "relative_path": str(path.relative_to(corpus_dir)),
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
        row["document_id"] = sha256[:16]
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


def build_inventory(
    corpus_dir: str | Path | None = None,
    output: str | Path | None = None,
    workers: int | None = None,
    recursive: bool = True,
) -> Path:
    corpus = Path(corpus_dir).expanduser().resolve() if corpus_dir else settings.corpus_dir
    output_path = Path(output).expanduser().resolve() if output else settings.inventory_path
    if not corpus.is_dir():
        raise NotADirectoryError(f"Corpus inválido: {corpus}")

    iterator = corpus.rglob("*.pdf") if recursive else corpus.glob("*.pdf")
    paths = sorted(path for path in iterator if path.is_file())
    resolved_workers = workers or max(1, min(8, os.cpu_count() or 4))
    rows: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=resolved_workers) as executor:
        futures = {executor.submit(inspect_pdf, path, corpus): path for path in paths}
        for index, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if index % 100 == 0 or index == len(paths):
                print(f"Inventariados: {index}/{len(paths)}")

    inventory = pd.DataFrame(rows).reindex(columns=INVENTORY_COLUMNS)
    if not inventory.empty:
        inventory = inventory.sort_values(["relative_path", "filename"]).reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(output_path, index=False, encoding="utf-8-sig")
    inventory[inventory["status"].ne("ok")].to_csv(
        output_path.with_name("inventory_errors.csv"), index=False, encoding="utf-8-sig"
    )
    print(f"Manifesto: {output_path}")
    return output_path


def sample_inventory(
    size: int = 100,
    source: str | Path | None = None,
    output: str | Path | None = None,
    seed: int = 42,
) -> Path:
    source_path = Path(source).expanduser().resolve() if source else settings.inventory_path
    output_path = (
        Path(output).expanduser().resolve()
        if output
        else settings.inventory_dir / "sample.csv"
    )
    inventory = pd.read_csv(source_path)
    valid = inventory[inventory["status"].eq("ok")].copy()
    if valid.empty:
        raise RuntimeError("Não há documentos válidos para amostrar.")
    sample_size = min(size, len(valid))
    sample = valid.sample(n=sample_size, random_state=seed).sort_values("relative_path")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Amostra: {output_path} ({len(sample)} documentos)")
    return output_path
