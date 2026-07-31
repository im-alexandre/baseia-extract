from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .settings import settings


@dataclass(frozen=True, slots=True)
class DocumentLayout:
    relative_pdf_path: Path
    pdf_path: Path
    document_dir: Path
    intermediate_dir: Path
    mineru_dir: Path
    canonical_dir: Path
    manifest_path: Path
    ir_path: Path
    structure_path: Path
    metadata_path: Path
    markdown_path: Path
    render_path: Path


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def document_layout(row: Mapping[str, Any]) -> DocumentLayout:
    relative_value = _text(row.get("relative_path")) or _text(
        row.get("filename")
    )
    if not relative_value:
        raise ValueError("Documento sem relative_path ou filename.")

    relative_pdf_path = Path(relative_value)
    if (
        relative_pdf_path.is_absolute()
        or ".." in relative_pdf_path.parts
        or relative_pdf_path.suffix.casefold() != ".pdf"
    ):
        raise ValueError(
            f"Caminho relativo de PDF inválido: {relative_value!r}"
        )

    physical_value = _text(row.get("path"))
    physical_path = (
        Path(physical_value).expanduser()
        if physical_value
        else Path()
    )
    if physical_value and physical_path.is_absolute():
        if physical_path.suffix.casefold() != ".pdf":
            raise ValueError(
                f"Path físico de PDF inválido: {physical_value!r}"
            )
        pdf_path = physical_path.resolve()
    else:
        pdf_path = (settings.document_store_dir / relative_pdf_path).resolve()
    directory_name = relative_pdf_path.stem.rstrip(" .")
    if not directory_name:
        directory_name = f"document-{row.get('document_id', 'unknown')}"
    document_dir = pdf_path.parent / directory_name
    intermediate_dir = document_dir / "intermediate"
    canonical_dir = document_dir / "canonical"
    return DocumentLayout(
        relative_pdf_path=relative_pdf_path,
        pdf_path=pdf_path,
        document_dir=document_dir,
        intermediate_dir=intermediate_dir,
        mineru_dir=intermediate_dir / "mineru",
        canonical_dir=canonical_dir,
        manifest_path=document_dir / "manifest.json",
        ir_path=canonical_dir / "document_ir.json",
        structure_path=canonical_dir / "structure.json",
        metadata_path=canonical_dir / "metadata.json",
        markdown_path=canonical_dir / "document.md",
        render_path=canonical_dir / "render.json",
    )
