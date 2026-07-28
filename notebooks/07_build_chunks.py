from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path.cwd()
if PROJECT_ROOT.name == "notebooks":
    PROJECT_ROOT = PROJECT_ROOT.parent

IR_ROOT = PROJECT_ROOT / "artifacts" / "ir_prototype"
STRUCTURE_ROOT = PROJECT_ROOT / "artifacts" / "structure_enrichment"
OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "chunks_prototype"

TARGET_CHARS = 2400
MAX_CHARS = 3600
MIN_CHARS = 300
OVERLAP_BLOCKS = 1

EXCLUDED_TEXT_ROLES = {
    "figure",
    "table",
    "chart",
    "equation",
    "code",
    "header",
    "footer",
    "page_number",
}

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} não contém um objeto JSON.")
    return data


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_text(value: str) -> str:
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def stable_chunk_id(
    document_id: str, section_id: str | None, block_ids: list[str]
) -> str:
    payload = "\n".join([document_id, section_id or "", *block_ids]).encode("utf-8")
    return f"chunk:{hashlib.sha256(payload).hexdigest()[:20]}"


def iter_page_blocks(document: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for page in document.get("pages", []) or []:
        for key in ("blocks", "discarded_blocks"):
            for block in page.get(key, []) or []:
                item = dict(block)
                item["_page_id"] = page.get("id")
                item["_page"] = page.get("page")
                yield item


def extract_block_text(block: dict[str, Any]) -> str:
    direct = block.get("text")
    if isinstance(direct, str) and direct.strip():
        return normalize_text(direct)

    lines: list[str] = []
    for line in block.get("lines", []) or []:
        direct_line = line.get("text")
        if isinstance(direct_line, str) and direct_line.strip():
            lines.append(direct_line)
            continue
        spans = line.get("spans", []) or []
        text = "".join(
            str(span.get("text") or span.get("content") or "") for span in spans
        )
        if text.strip():
            lines.append(text)
    return normalize_text("\n".join(lines))


def build_section_paths(structure: dict[str, Any]) -> dict[str, list[str]]:
    by_id = {
        section["id"]: section
        for section in structure.get("sections", []) or []
        if isinstance(section, dict) and section.get("id")
    }
    cache: dict[str, list[str]] = {}

    def resolve(section_id: str) -> list[str]:
        if section_id in cache:
            return cache[section_id]
        section = by_id.get(section_id)
        if not section:
            return []
        parent_id = section.get("parent_id")
        path = resolve(parent_id) if parent_id else []
        title = normalize_text(str(section.get("title") or ""))
        if title:
            path = [*path, title]
        cache[section_id] = path
        return path

    for section_id in by_id:
        resolve(section_id)
    return cache


def find_document_ir(structure_path: Path) -> Path:
    relative = structure_path.relative_to(STRUCTURE_ROOT)
    candidate = IR_ROOT / relative.parent / "document_ir.json"
    if candidate.exists():
        return candidate
    matches = list(IR_ROOT.rglob(f"{relative.parent.name}/document_ir.json"))
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"document_ir.json não encontrado para {structure_path}")


@dataclass(slots=True)
class BlockUnit:
    block_id: str
    page_id: str | None
    page: int | None
    section_id: str | None
    role: str
    source_type: str
    text: str
    asset_ids: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text)


def build_units(
    document: dict[str, Any],
    structure: dict[str, Any],
) -> tuple[list[BlockUnit], dict[str, list[str]]]:
    """
    Reconcilia os blocos do DocumentIR com as anotações estruturais.

    O structure_ir possui IDs determinísticos, mas os document_ir.json
    antigos podem não conter esses IDs persistidos. Como a etapa 06 cria
    as anotações na mesma ordem dos blocos de conteúdo, associamos ambos
    por `reading_order`.
    """
    raw_content_blocks: list[dict[str, Any]] = []

    for page in document.get("pages", []) or []:
        page_id = page.get("id")
        page_number = page.get("page")

        for block in page.get("blocks", []) or []:
            item = dict(block)
            item["_page_id"] = page_id
            item["_page"] = page_number
            raw_content_blocks.append(item)

    ordered_annotations = sorted(
        (
            item
            for item in structure.get("annotations", []) or []
            if isinstance(item, dict)
        ),
        key=lambda item: int(item.get("reading_order", 0)),
    )

    if len(raw_content_blocks) != len(ordered_annotations):
        raise ValueError(
            "Não foi possível reconciliar DocumentIR e StructureIR: "
            f"{len(raw_content_blocks)} blocos de conteúdo contra "
            f"{len(ordered_annotations)} anotações."
        )

    block_index: dict[str, dict[str, Any]] = {}

    for block, annotation in zip(
        raw_content_blocks,
        ordered_annotations,
        strict=True,
    ):
        block_id = annotation.get("block_id")

        if not isinstance(block_id, str) or not block_id:
            raise ValueError(f"Anotação estrutural sem block_id válido: {annotation}")

        block["_page_id"] = annotation.get(
            "page_id",
            block.get("_page_id"),
        )
        block["_page"] = annotation.get(
            "page",
            block.get("_page"),
        )
        block["id"] = block_id

        block_index[block_id] = block

    annotations = {
        item["block_id"]: item for item in ordered_annotations if item.get("block_id")
    }

    assets_by_block: dict[str, list[str]] = defaultdict(list)

    for asset in structure.get("assets", []) or []:
        if not isinstance(asset, dict):
            continue

        block_id = asset.get("block_id")
        asset_id = asset.get("id")

        if block_id and asset_id:
            assets_by_block[str(block_id)].append(str(asset_id))

    units: list[BlockUnit] = []

    for block_id in (
        structure.get(
            "primary_flow_block_ids",
            [],
        )
        or []
    ):
        block = block_index.get(block_id)

        if block is None:
            raise KeyError(f"Bloco do fluxo principal não encontrado: {block_id}")

        annotation = annotations.get(block_id)

        if annotation is None:
            raise KeyError(f"Anotação não encontrada para o bloco: {block_id}")

        role = str(annotation.get("role") or block.get("type") or "other").lower()

        source_type = str(
            annotation.get("source_type") or block.get("type") or "unknown"
        ).lower()

        text = "" if role in EXCLUDED_TEXT_ROLES else extract_block_text(block)

        units.append(
            BlockUnit(
                block_id=block_id,
                page_id=annotation.get("page_id"),
                page=annotation.get("page"),
                section_id=annotation.get("section_id"),
                role=role,
                source_type=source_type,
                text=text,
                asset_ids=assets_by_block.get(block_id, []),
            )
        )

    return units, build_section_paths(structure)


def render_chunk_text(units: list[BlockUnit], section_path: list[str]) -> str:
    pieces = [" > ".join(section_path)] if section_path else []
    pieces.extend(unit.text for unit in units if unit.text)
    return normalize_text("\n\n".join(pieces))


def make_chunk(
    document: dict[str, Any],
    units: list[BlockUnit],
    section_path: list[str],
    ordinal: int,
) -> dict[str, Any]:
    block_ids = [unit.block_id for unit in units]
    pages = [unit.page for unit in units if isinstance(unit.page, int)]
    roles = Counter(unit.role for unit in units)
    source_types = Counter(unit.source_type for unit in units)
    section_id = units[0].section_id if units else None
    text = render_chunk_text(units, section_path)
    return {
        "id": stable_chunk_id(str(document.get("id") or ""), section_id, block_ids),
        "document_id": document.get("id"),
        "source_name": document.get("source_name"),
        "source_path": document.get("source_path"),
        "source_sha256": document.get("source_sha256"),
        "ordinal": ordinal,
        "section_id": section_id,
        "section_path": section_path,
        "block_ids": block_ids,
        "page_start": min(pages) if pages else None,
        "page_end": max(pages) if pages else None,
        "text": text,
        "char_count": len(text),
        "token_count_estimate": estimate_tokens(text),
        "asset_ids": sorted({asset for unit in units for asset in unit.asset_ids}),
        "contains_list": roles["list"] > 0,
        "contains_equation": roles["equation"] > 0,
        "contains_table": roles["table"] > 0,
        "contains_figure": roles["figure"] > 0,
        "role_counts": dict(sorted(roles.items())),
        "source_type_counts": dict(sorted(source_types.items())),
        "overlap_block_ids": [],
    }


def build_chunks_for_document(
    document: dict[str, Any], structure: dict[str, Any]
) -> list[dict[str, Any]]:
    units, section_paths = build_units(document, structure)
    grouped: dict[str | None, list[BlockUnit]] = defaultdict(list)
    order: list[str | None] = []
    for unit in units:
        if unit.section_id not in grouped:
            order.append(unit.section_id)
        grouped[unit.section_id].append(unit)

    chunks: list[dict[str, Any]] = []
    ordinal = 0

    for section_id in order:
        section_units = grouped[section_id]
        current: list[BlockUnit] = []
        current_chars = 0

        def flush() -> None:
            nonlocal current, current_chars, ordinal
            if not any(unit.text for unit in current):
                current, current_chars = [], 0
                return
            chunk = make_chunk(
                document, current, section_paths.get(section_id or "", []), ordinal
            )
            if (
                chunk["char_count"] >= MIN_CHARS
                or len(current) == len(section_units)
                or not chunks
            ):
                chunks.append(chunk)
                ordinal += 1
            elif chunks and chunks[-1]["section_id"] == section_id:
                previous = chunks.pop()
                merged_ids = list(
                    dict.fromkeys(previous["block_ids"] + chunk["block_ids"])
                )
                merged_units = [
                    unit for unit in section_units if unit.block_id in set(merged_ids)
                ]
                chunks.append(
                    make_chunk(
                        document,
                        merged_units,
                        section_paths.get(section_id or "", []),
                        previous["ordinal"],
                    )
                )
            overlap = current[-OVERLAP_BLOCKS:] if OVERLAP_BLOCKS > 0 else []
            current = list(overlap)
            current_chars = sum(unit.char_count for unit in current)

        for unit in section_units:
            if not unit.text:
                current.append(unit)
                continue
            if current and current_chars + unit.char_count > MAX_CHARS:
                flush()
            current.append(unit)
            current_chars += unit.char_count
            if current_chars >= TARGET_CHARS:
                flush()
        if current:
            flush()

    seen: set[str] = set()
    for chunk in chunks:
        chunk["overlap_block_ids"] = [
            block_id for block_id in chunk["block_ids"] if block_id in seen
        ]
        seen.update(chunk["block_ids"])
    return chunks


def validate_document_chunks(
    document: dict[str, Any], structure: dict[str, Any], chunks: list[dict[str, Any]]
) -> dict[str, Any]:
    primary_ids = structure.get("primary_flow_block_ids", []) or []
    appearances = Counter(
        block_id for chunk in chunks for block_id in chunk.get("block_ids", [])
    )
    expected, represented = set(primary_ids), set(appearances)
    oversized = [chunk["id"] for chunk in chunks if chunk["char_count"] > MAX_CHARS]
    duplicates_without_overlap: list[str] = []
    for block_id, count in appearances.items():
        overlap_mentions = sum(
            block_id in chunk.get("overlap_block_ids", []) for chunk in chunks
        )
        if count > 1 and overlap_mentions < count - 1:
            duplicates_without_overlap.append(block_id)
    missing = sorted(expected - represented)
    unexpected = sorted(represented - expected)
    return {
        "document_id": document.get("id"),
        "source_name": document.get("source_name"),
        "valid": not (missing or unexpected or oversized or duplicates_without_overlap),
        "chunk_count": len(chunks),
        "primary_block_count": len(primary_ids),
        "represented_block_count": len(represented),
        "missing_block_ids": missing,
        "unexpected_block_ids": unexpected,
        "oversized_chunk_ids": oversized,
        "undersized_chunk_ids": [
            chunk["id"] for chunk in chunks if chunk["char_count"] < MIN_CHARS
        ],
        "duplicate_without_overlap_block_ids": sorted(duplicates_without_overlap),
    }


def main() -> None:
    structure_paths = sorted(STRUCTURE_ROOT.rglob("structure_ir.json"))
    if not structure_paths:
        raise FileNotFoundError(
            f"Nenhum structure_ir.json encontrado em {STRUCTURE_ROOT}"
        )

    all_chunks: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    print(f"structure_ir.json encontrados: {len(structure_paths)}")

    for index, structure_path in enumerate(structure_paths, start=1):
        document = load_json(find_document_ir(structure_path))
        structure = load_json(structure_path)
        chunks = build_chunks_for_document(document, structure)
        if not chunks:
            raise RuntimeError(
                f"Nenhum chunk foi produzido para "
                f"{document.get('source_name')}. "
                f"primary_flow_block_ids="
                f"{len(structure.get('primary_flow_block_ids', []))}"
            )

        validation = validate_document_chunks(document, structure, chunks)

        relative_dir = structure_path.relative_to(STRUCTURE_ROOT).parent
        output_dir = OUTPUT_ROOT / relative_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        with (output_dir / "chunks.jsonl").open("w", encoding="utf-8") as file:
            for chunk in chunks:
                file.write(json.dumps(chunk, ensure_ascii=False) + "\n")
        write_json(output_dir / "chunk_validation.json", validation)

        all_chunks.extend(chunks)
        validations.append(validation)
        for chunk in chunks:
            diagnostics.append(
                {
                    "document_id": chunk["document_id"],
                    "source_name": chunk["source_name"],
                    "chunk_id": chunk["id"],
                    "ordinal": chunk["ordinal"],
                    "section_id": chunk["section_id"],
                    "section_path": " > ".join(chunk["section_path"]),
                    "page_start": chunk["page_start"],
                    "page_end": chunk["page_end"],
                    "char_count": chunk["char_count"],
                    "token_count_estimate": chunk["token_count_estimate"],
                    "block_count": len(chunk["block_ids"]),
                    "overlap_block_count": len(chunk["overlap_block_ids"]),
                    "asset_count": len(chunk["asset_ids"]),
                }
            )
        print(
            f"[{index:03d}/{len(structure_paths):03d}] {'OK' if validation['valid'] else 'ERRO'} {document.get('source_name')} chunks={len(chunks)}"
        )

    with (OUTPUT_ROOT / "chunks.jsonl").open("w", encoding="utf-8") as file:
        for chunk in all_chunks:
            file.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    if diagnostics:
        with (OUTPUT_ROOT / "chunk_diagnostics.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as file:
            writer = csv.DictWriter(file, fieldnames=list(diagnostics[0]))
            writer.writeheader()
            writer.writerows(diagnostics)

    char_counts = [chunk["char_count"] for chunk in all_chunks]
    summary = {
        "documents": len(structure_paths),
        "chunks": len(all_chunks),
        "valid_documents": sum(row["valid"] for row in validations),
        "invalid_documents": sum(not row["valid"] for row in validations),
        "target_chars": TARGET_CHARS,
        "max_chars": MAX_CHARS,
        "min_chars": MIN_CHARS,
        "overlap_blocks": OVERLAP_BLOCKS,
        "mean_chars": round(sum(char_counts) / len(char_counts), 2)
        if char_counts
        else 0,
        "min_observed_chars": min(char_counts) if char_counts else 0,
        "max_observed_chars": max(char_counts) if char_counts else 0,
    }
    write_json(OUTPUT_ROOT / "chunk_summary.json", summary)
    write_json(
        OUTPUT_ROOT / "chunk_validation_report.json",
        {"valid": all(row["valid"] for row in validations), "documents": validations},
    )

    print("\nChunking concluído.")
    print(f"Chunks: {len(all_chunks)}")
    print(f"Saída: {OUTPUT_ROOT.resolve()}")


if __name__ == "__main__":
    main()
