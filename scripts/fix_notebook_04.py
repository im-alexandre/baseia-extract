from __future__ import annotations

from pathlib import Path


NOTEBOOK = Path("notebooks/04_build_ir_prototype.py")
OLD = "    document = build_document_ir(middle_path)"
NEW = "    document, middle_payload = build_document_ir(middle_path)"


def main() -> None:
    source = NOTEBOOK.read_text(encoding="utf-8")

    if NEW in source:
        print(f"{NOTEBOOK} já está corrigido.")
        return

