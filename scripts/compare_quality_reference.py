from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


def _walk_blocks(blocks: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for block in blocks:
        yield block
        yield from _walk_blocks(block.get("blocks") or ())


def _iter_spans(block: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for line in block.get("lines") or ():
        yield from line.get("spans") or ()


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _metrics(document: dict[str, Any]) -> dict[str, Any]:
    pages = document.get("pages") or []
    content_blocks = [
        block
        for page in pages
        for block in _walk_blocks(page.get("blocks") or ())
    ]
    discarded_blocks = [
        block
        for page in pages
        for block in _walk_blocks(page.get("discarded_blocks") or ())
    ]
    blocks = [*content_blocks, *discarded_blocks]
    lines = [line for block in blocks for line in block.get("lines") or ()]
    spans = [span for block in blocks for span in _iter_spans(block)]
    text = _normalized_text(
        " ".join(
            str(span.get("content") or span.get("text") or "")
            for span in spans
        )
    )
    block_types = Counter(str(block.get("type") or "unknown") for block in blocks)
    span_types = Counter(str(span.get("type") or "unknown") for span in spans)
    image_paths = {
        str(node["image_path"])
        for node in [*blocks, *spans]
        if node.get("image_path")
    }
    html_tables = sum(
        1
        for node in [*blocks, *spans]
        if "<table" in str(node.get("html") or "").casefold()
    )
    ids = [
        document.get("id"),
        *(page.get("id") for page in pages),
        *(block.get("id") for block in blocks),
        *(line.get("id") for line in lines),
        *(span.get("id") for span in spans),
    ]
    return {
        "pages": len(pages),
        "content_blocks": len(content_blocks),
        "discarded_blocks": len(discarded_blocks),
        "lines": len(lines),
        "spans": len(spans),
        "text_characters": len(text),
        "text": text,
        "block_types": dict(sorted(block_types.items())),
        "span_types": dict(sorted(span_types.items())),
        "images": len(image_paths),
        "image_paths": sorted(image_paths),
        # O mesmo elemento pode aparecer no bloco, no span e como HTML.
        # O maior contador representa a quantidade sem triplicar o elemento.
        "tables": max(
            block_types["table"],
            span_types["table"],
            html_tables,
        ),
        "interline_equations": max(
            block_types["interline_equation"],
            span_types["interline_equation"],
        ),
        "inline_equations": (
            block_types["inline_equation"] + span_types["inline_equation"]
        ),
        "nodes_with_ids": sum(bool(value) for value in ids),
        "nodes_total_for_ids": len(ids),
        "root_attribute_keys": sorted((document.get("attributes") or {}).keys()),
        "has_middle_sha256": bool(document.get("middle_sha256")),
        "has_source_pdf_sha256": bool(document.get("source_pdf_sha256")),
        "has_document_id": bool(document.get("id")),
    }


def _delta(old: dict[str, Any], current: dict[str, Any], key: str) -> int:
    return int(current[key]) - int(old[key])


def compare(old_root: Path, current_ir_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for old_path in sorted(old_root.rglob("document_ir.json")):
        document_id = next(
            (
                part
                for part in old_path.parts
                if re.fullmatch(r"[0-9a-f]{16}", part)
            ),
            "",
        )
        current_path = current_ir_root / document_id / "document_ir.json"
        old_document = json.loads(old_path.read_text(encoding="utf-8"))
        old = _metrics(old_document)
        if not current_path.is_file():
            rows.append(
                {
                    "document_id": document_id,
                    "source_name": old_path.parent.parent.name,
                    "current_available": False,
                }
            )
            continue
        current_document = json.loads(current_path.read_text(encoding="utf-8"))
        current = _metrics(current_document)
        ratio = SequenceMatcher(
            None,
            old["text"],
            current["text"],
            autojunk=False,
        ).ratio()
        rows.append(
            {
                "document_id": document_id,
                "source_name": old_path.parent.parent.name,
                "current_available": True,
                "text_similarity": round(ratio, 6),
                "old": {key: value for key, value in old.items() if key != "text"},
                "current": {
                    key: value for key, value in current.items() if key != "text"
                },
                "delta": {
                    key: _delta(old, current, key)
                    for key in (
                        "pages",
                        "content_blocks",
                        "discarded_blocks",
                        "lines",
                        "spans",
                        "text_characters",
                        "images",
                        "tables",
                        "interline_equations",
                        "inline_equations",
                        "nodes_with_ids",
                    )
                },
                "block_types_added": dict(
                    Counter(current["block_types"]) - Counter(old["block_types"])
                ),
                "block_types_removed": dict(
                    Counter(old["block_types"]) - Counter(current["block_types"])
                ),
                "span_types_added": dict(
                    Counter(current["span_types"]) - Counter(old["span_types"])
                ),
                "span_types_removed": dict(
                    Counter(old["span_types"]) - Counter(current["span_types"])
                ),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-root", type=Path, required=True)
    parser.add_argument("--current-ir-root", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args()
    rows = compare(args.old_root, args.current_ir_root)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    flat_rows = []
    for row in rows:
        flat = {
            "document_id": row["document_id"],
            "source_name": row.get("source_name"),
            "current_available": row["current_available"],
            "text_similarity": row.get("text_similarity"),
        }
        if row["current_available"]:
            for version in ("old", "current", "delta"):
                for key, value in row[version].items():
                    if isinstance(value, int | float | bool):
                        flat[f"{version}_{key}"] = value
        flat_rows.append(flat)
    fieldnames = sorted({key for row in flat_rows for key in row})
    with args.csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_rows)
    print(f"Comparados: {sum(row['current_available'] for row in rows)}/{len(rows)}")
    print(args.json)
    print(args.csv)


if __name__ == "__main__":
    main()
