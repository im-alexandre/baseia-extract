"""Renderização semântica e lossless dos artefatos ``middle.json`` do MinerU.

Esta etapa fica deliberadamente entre a extração e o chunking: persiste o IR
canônico, sua estrutura derivada e uma representação Markdown para revisão.
Ela não altera o inventário, o PDF, nem o artefato MinerU de origem.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import tempfile
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from json import JSONDecodeError
from typing import Any

import pandas as pd

from .ir import DocumentIR, build_document_ir, validate_document_ir
from .settings import settings
from .structure import enrich_document, validate_structure


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _atomic_write_json(path: Path, value: Any) -> None:
    _atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _html_to_markdown(html: str) -> str:
    """Converte HTML MinerU com o conversor maduro ``markdownify``.

    ``sup`` e ``sub`` permanecem como HTML semântico, pois CommonMark não tem
    sintaxe nativa para eles. Tabelas representáveis são emitidas pelo próprio
    conversor como tabelas Markdown, sem parser ou regex local.
    """
    try:
        from markdownify import markdownify
    except ImportError as error:
        raise RuntimeError(
            "A renderização de HTML requer a dependência 'markdownify'. "
            "Instale-a no ambiente do projeto antes de executar poe render."
        ) from error
    return markdownify(
        html,
        heading_style="ATX",
        bullets="-",
        strong_em_symbol="*",
        em_symbol="_",
        sub_symbol="<sub>",
        sup_symbol="<sup>",
        escape_asterisks=False,
        escape_underscores=False,
    ).strip("\n")


def _text_or_html_to_markdown(value: str) -> str:
    """Converte markup embutido somente quando o parser encontra uma tag."""
    from bs4 import BeautifulSoup

    if BeautifulSoup(value, "html.parser").find() is None:
        return value
    return _html_to_markdown(value)


def _block_lines(
    block: Any,
    *,
    middle_path: Path,
    markdown_path: Path,
) -> tuple[str, list[str]]:
    """Reproduz o texto físico do bloco sem corrigir ou normalizar conteúdo."""
    if not block.lines:
        content = block.content if block.content is not None else (block.text or "")
        return content, []

    lines: list[str] = []
    missing_assets: list[str] = []
    for line in block.lines:
        spans: list[str] = []
        for span in line.spans:
            if span.html is not None:
                spans.append(_html_to_markdown(span.html))
            elif span.latex is not None:
                if span.type == "interline_equation":
                    spans.append("$$\n" + span.latex + "\n$$")
                else:
                    spans.append("$" + span.latex + "$")
            elif span.type in {"inline_equation", "interline_equation"}:
                equation = (
                    span.content
                    if span.content is not None
                    else (span.text or "")
                )
                if span.type == "interline_equation":
                    spans.append("$$\n" + equation + "\n$$")
                else:
                    spans.append("$" + equation + "$")
            elif span.image_path is not None:
                reference, missing_asset = _resolved_image_reference(
                    span.image_path,
                    middle_path=middle_path,
                    markdown_path=markdown_path,
                )
                spans.append(_markdown_image(reference))
                if missing_asset is not None:
                    missing_assets.append(missing_asset)
            elif span.content is not None:
                spans.append(_text_or_html_to_markdown(span.content))
            elif span.text is not None:
                spans.append(_text_or_html_to_markdown(span.text))
        lines.append("".join(spans))
    return "\n".join(lines), missing_assets


def _resolved_image_reference(
    image_path: str,
    *,
    middle_path: Path,
    markdown_path: Path,
) -> tuple[str, str | None]:
    """Resolve uma imagem já produzida pelo MinerU, sem copiá-la ou inventá-la."""
    source_directory = middle_path.parent
    declared = Path(image_path)
    candidates = [
        source_directory / declared,
        source_directory / "images" / declared.name,
        source_directory / declared.name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return (
                Path(os.path.relpath(candidate, markdown_path.parent)).as_posix(),
                None,
            )
    matches = sorted(path for path in source_directory.rglob(declared.name) if path.is_file())
    if matches:
        return (
            Path(os.path.relpath(matches[0], markdown_path.parent)).as_posix(),
            None,
        )
    return image_path, image_path


def _markdown_image(reference: str) -> str:
    """Emite destino entre ``<>`` para caminhos relativos com espaços."""
    return f"![](<{reference}>)"


def _markdown_for_block(
    block: Any,
    *,
    role: str,
    middle_path: Path,
    markdown_path: Path,
) -> tuple[str, list[str]]:
    """Renderiza uma árvore de blocos sem descartar captions ou assets filhos."""
    missing_assets: list[str] = []
    if block.html is not None:
        content = _html_to_markdown(block.html)
    elif block.latex is not None:
        content = "$$\n" + block.latex + "\n$$"
    elif block.image_path is not None:
        reference, missing_asset = _resolved_image_reference(
            block.image_path,
            middle_path=middle_path,
            markdown_path=markdown_path,
        )
        if missing_asset is not None:
            missing_assets.append(missing_asset)
        content = _markdown_image(reference)
    else:
        content, line_missing_assets = _block_lines(
            block,
            middle_path=middle_path,
            markdown_path=markdown_path,
        )
        missing_assets.extend(line_missing_assets)
    if content and role == "title":
        level = max(1, min(6, block.level or 1))
        # Uma única heading pode conter quebras físicas sem reescrever letras.
        content = "#" * level + " " + content.replace("\n", "<br>\n")

    children = getattr(block, "blocks", [])
    rendered_children: list[str] = []
    for child in children:
        child_role = "title" if getattr(child, "type", None) == "title" else str(role)
        child_content, child_missing_assets = _markdown_for_block(
            child,
            role=child_role,
            middle_path=middle_path,
            markdown_path=markdown_path,
        )
        missing_assets.extend(child_missing_assets)
        if child_content:
            rendered_children.append(child_content)
    parts = ([content] if content else []) + rendered_children
    return "\n\n".join(parts), missing_assets


def _render_markdown(
    document: DocumentIR,
    structure: Any,
    *,
    middle_path: Path,
    markdown_path: Path,
) -> tuple[str, list[str]]:
    blocks = {block.id: block for page in document.pages for block in page.blocks}
    annotations = sorted(structure.annotations, key=lambda item: item.reading_order)
    rendered: list[str] = []
    missing_assets: list[str] = []
    for annotation in annotations:
        if annotation.excluded_from_primary_flow:
            continue
        block = blocks[annotation.block_id]
        content, block_missing_assets = _markdown_for_block(
            block,
            role=str(annotation.role),
            middle_path=middle_path,
            markdown_path=markdown_path,
        )
        missing_assets.extend(block_missing_assets)
        if content:
            rendered.append(content)
    return "\n\n".join(rendered) + ("\n" if rendered else ""), missing_assets


def _iter_blocks(document: DocumentIR) -> Any:
    def walk(block: Any) -> Any:
        yield block
        for child in block.blocks:
            yield from walk(child)

    for page in document.pages:
        for block in page.blocks:
            yield from walk(block)


def _mineru_markdown_path(middle_path: Path) -> Path | None:
    expected = middle_path.with_name(
        middle_path.name.removesuffix("_middle.json") + ".md"
    )
    if expected.is_file():
        return expected
    candidates = sorted(
        path for path in middle_path.parent.glob("*.md") if path.is_file()
    )
    return candidates[0] if len(candidates) == 1 else None


def _pdf_table_markdown_by_html(
    document: DocumentIR,
    source_pdf_path: Path | None,
) -> dict[str, str]:
    """Extrai tabelas digitais do PDF com ``pdfplumber`` e serializa via tabulate."""
    if source_pdf_path is None or not source_pdf_path.is_file():
        return {}

    import pdfplumber
    from bs4 import BeautifulSoup
    from tabulate import tabulate

    replacements: dict[str, str] = {}
    with pdfplumber.open(source_pdf_path) as pdf:
        for page in document.pages:
            table_blocks = [
                (block, html)
                for block in _iter_blocks_on_page(page.blocks)
                if block.type == "table"
                if (html := _first_html(block)) is not None
            ]
            if not table_blocks or not 0 <= page.page < len(pdf.pages):
                continue
            pdf_page = pdf.pages[page.page]
            candidates = pdf_page.extract_tables()
            if not candidates:
                candidates = pdf_page.extract_tables(
                    {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "text",
                    }
                )
            candidates = [
                [
                    ["" if cell is None else str(cell) for cell in row]
                    for row in table
                    if any(cell not in (None, "") for cell in row)
                ]
                for table in candidates
                if table
            ]
            candidates = [table for table in candidates if table]
            if len(candidates) != len(table_blocks):
                continue

            for (block, block_html), rows in zip(
                table_blocks,
                candidates,
                strict=True,
            ):
                original_rows = [
                    [
                        cell.get_text(" ", strip=False)
                        for cell in row.find_all(["th", "td"])
                    ]
                    for row in BeautifulSoup(
                        block_html,
                        "html.parser",
                    ).find_all("tr")
                ]
                width = max(len(row) for row in rows)
                if width == 2 and all(len(row) == 2 for row in original_rows):
                    rows = [
                        [
                            original_rows[index][0],
                            row[1],
                        ]
                        for index, row in enumerate(rows)
                        if index < len(original_rows)
                    ]
                elif width == 1:
                    merged: list[list[str]] = []
                    for row in rows:
                        value = row[0]
                        if (
                            merged
                            and ":" in merged[-1][0]
                            and ":" not in value
                        ):
                            merged[-1][0] += " " + value
                        else:
                            merged.append([value])
                    rows = merged
                normalized_rows = [
                    [" ".join(cell.splitlines()) for cell in row]
                    for row in rows
                ]
                original_text = BeautifulSoup(
                    block_html,
                    "html.parser",
                ).get_text(" ", strip=True)
                extracted_text = " ".join(
                    cell for row in normalized_rows for cell in row
                )
                if (
                    max(
                        (
                            len(word)
                            for word in extracted_text.split()
                        ),
                        default=0,
                    )
                    > 24
                    and len(original_text.split()) > len(extracted_text.split())
                ):
                    if block.bbox is None:
                        continue
                    cropped_text = pdf_page.crop(
                        tuple(block.bbox)
                    ).extract_text(x_tolerance=1)
                    if not cropped_text:
                        continue
                    normalized_rows = []
                    for line in cropped_text.splitlines():
                        value = line.strip()
                        if not value:
                            continue
                        if (
                            normalized_rows
                            and ":" in normalized_rows[-1][0]
                            and ":" not in value
                        ):
                            normalized_rows[-1][0] += " " + value
                        else:
                            normalized_rows.append([value])
                    width = 1
                semantic_title: str | None = None
                if width == 1:
                    for index, row in enumerate(normalized_rows):
                        if re.match(
                            r"(?i)^t[ií]tulo\s+(?:do\s+)?(?:t(?:i)?\s*2|trabalho)\s*:",
                            row[0],
                        ):
                            semantic_title = row[0]
                            normalized_rows = [
                                item
                                for row_index, item in enumerate(normalized_rows)
                                if row_index != index
                            ]
                            break
                table_markdown = tabulate(
                    normalized_rows,
                    headers=[""] * width,
                    tablefmt="github",
                    disable_numparse=True,
                )
                if semantic_title is not None:
                    table_markdown += f"\n\n# {semantic_title}"
                replacements[block_html] = table_markdown
    return replacements


def _pdf_corrupt_span_replacements(
    document: DocumentIR,
    source_pdf_path: Path | None,
) -> dict[str, str]:
    """Reconstrói spans com U+FFFD usando palavras e geometria do PDF digital."""
    if source_pdf_path is None or not source_pdf_path.is_file():
        return {}

    import pdfplumber

    replacements: dict[str, str] = {}
    with pdfplumber.open(source_pdf_path) as pdf:
        for page in document.pages:
            if not 0 <= page.page < len(pdf.pages):
                continue
            for block in _iter_blocks_on_page(page.blocks):
                for line in block.lines:
                    for span in line.spans:
                        value = (
                            span.content
                            if span.content is not None
                            else span.text
                        )
                        if value is None or "\ufffd" not in value:
                            continue
                        if span.bbox is None:
                            raise ValueError(
                                f"Span corrompido sem bbox: {span.id}"
                            )
                        words = pdf.pages[page.page].crop(
                            tuple(span.bbox)
                        ).extract_words(
                            x_tolerance=1,
                            y_tolerance=3,
                            extra_attrs=["fontname", "size"],
                        )
                        words = sorted(words, key=lambda item: item["x0"])
                        if not words:
                            raise ValueError(
                                f"Span corrompido sem texto PDF: {span.id}"
                            )
                        baseline_size = max(float(word["size"]) for word in words)
                        pieces: list[str] = []
                        previous: dict[str, Any] | None = None
                        for word in words:
                            text = unicodedata.normalize("NFKC", word["text"])
                            superscript = float(word["size"]) < baseline_size * 0.85
                            if superscript:
                                text = f"<sup>{text}</sup>"
                            if previous is not None:
                                gap = float(word["x0"]) - float(previous["x1"])
                                previous_text = unicodedata.normalize(
                                    "NFKC",
                                    previous["text"],
                                )
                                if (
                                    gap > 1
                                    and not superscript
                                    and not previous_text.endswith(
                                        ("(", "[", "{")
                                    )
                                    and text not in {")", "]", "}", ",", ".", ":", ";"}
                                ):
                                    pieces.append(" ")
                            pieces.append(text)
                            previous = word
                        replacements[span.id] = "".join(pieces)
    return replacements


def _pdf_inline_equation_replacements(
    document: DocumentIR,
    source_pdf_path: Path | None,
) -> dict[str, str]:
    """Recupera glifos tipográficos classificados como equação inline.

    Neste corpus, os cinco casos são notação editorial (``nº``, ``5º`` e
    ``T₂``), não fórmulas matemáticas. A geometria/fontes do PDF preserva a
    representação original melhor que o LaTeX espaçado produzido pelo OCR.
    """
    if source_pdf_path is None or not source_pdf_path.is_file():
        return {}

    import pdfplumber

    replacements: dict[str, str] = {}
    with pdfplumber.open(source_pdf_path) as pdf:
        for page in document.pages:
            if not 0 <= page.page < len(pdf.pages):
                continue
            for block in _iter_blocks_on_page(page.blocks):
                for line in block.lines:
                    for span_index, span in enumerate(line.spans):
                        if span.type != "inline_equation" or span.bbox is None:
                            continue
                        words = pdf.pages[page.page].crop(
                            tuple(span.bbox)
                        ).extract_words(
                            x_tolerance=1,
                            y_tolerance=3,
                            extra_attrs=["size"],
                        )
                        words = sorted(words, key=lambda item: float(item["x0"]))
                        if not words:
                            continue
                        baseline_size = max(float(word["size"]) for word in words)
                        baseline_top = min(
                            float(word["top"])
                            for word in words
                            if float(word["size"]) >= baseline_size * 0.85
                        )
                        pieces: list[str] = []
                        previous: dict[str, Any] | None = None
                        for word in words:
                            text = unicodedata.normalize("NFC", str(word["text"]))
                            smaller = float(word["size"]) < baseline_size * 0.85
                            if smaller:
                                if float(word["top"]) > baseline_top + 1:
                                    text = f"<sub>{text}</sub>"
                                else:
                                    text = f"<sup>{text}</sup>"
                            if previous is not None:
                                gap = float(word["x0"]) - float(previous["x1"])
                                if gap > 1 and not smaller:
                                    pieces.append(" ")
                            pieces.append(text)
                            previous = word
                        replacement = "".join(pieces)
                        next_span = (
                            line.spans[span_index + 1]
                            if span_index + 1 < len(line.spans)
                            else None
                        )
                        next_text = (
                            next_span.content or next_span.text or ""
                            if next_span is not None
                            else ""
                        )
                        if replacement.endswith(":") and next_text.lstrip().startswith(":"):
                            replacement = replacement[:-1]
                        replacements[span.id] = replacement
    return replacements


def _restore_missing_line_separators(document: DocumentIR, markdown: str) -> str:
    """Restaura separadores que o Markdown oficial omitiu entre linhas do IR."""
    rendered = markdown
    for block in _iter_blocks(document):
        physical_lines = [
            "".join(span.content or span.text or "" for span in line.spans)
            for line in block.lines
        ]
        metadata_block = any(
            re.match(
                r"(?i)^(?:(?:nome|n[uú]mero|data|t[ií]tulo|professor)\b|"
                r"disciplina(?:\s+de\s+direito(?:\s*[–-]\s*IME)?\s*$|\s*:|$))",
                line,
            )
            for line in physical_lines
        )
        if not metadata_block and len(physical_lines) > 1:
            separated_paragraph = "\n\n".join(physical_lines)
            if separated_paragraph in rendered:
                rendered = rendered.replace(
                    separated_paragraph,
                    " ".join(physical_lines),
                )
        for left, right in zip(physical_lines, physical_lines[1:], strict=False):
            if not left or not right:
                continue
            source_joins = (
                (left + right, left + " " + right)
                if metadata_block
                else (left + right,)
            )
            separator = "\n\n" if metadata_block else " "
            for source_join in source_joins:
                if source_join in rendered:
                    rendered = rendered.replace(
                        source_join,
                        left + separator + right,
                    )
                    break
    return rendered


def _repair_spacing_accents(value: str) -> str:
    """Recompõe acentos espaçadores emitidos pelo texto TeX do PDF."""
    repaired = value.replace("\\`", "`")
    combining_by_spacing = {
        "´": "\N{COMBINING ACUTE ACCENT}",
        "˜": "\N{COMBINING TILDE}",
        "¸": "\N{COMBINING CEDILLA}",
        "ˆ": "\N{COMBINING CIRCUMFLEX ACCENT}",
        "¨": "\N{COMBINING DIAERESIS}",
        "`": "\N{COMBINING GRAVE ACCENT}",
    }
    for spacing, combining in combining_by_spacing.items():
        repaired = re.sub(
            re.escape(spacing) + r"([A-Za-zı])",
            lambda match: ("i" if match.group(1) == "ı" else match.group(1))
            + combining,
            repaired,
        )
    return unicodedata.normalize("NFC", repaired)


def _iter_blocks_on_page(blocks: list[Any]) -> Any:
    for block in blocks:
        yield block
        yield from _iter_blocks_on_page(block.blocks)


def _first_html(block: Any) -> str | None:
    if block.html is not None:
        return block.html
    for line in block.lines:
        for span in line.spans:
            if span.html is not None:
                return span.html
    for child in block.blocks:
        if (html := _first_html(child)) is not None:
            return html
    return None


def _render_mineru_markdown(
    document: DocumentIR,
    *,
    source_path: Path,
    source_pdf_path: Path | None,
    middle_path: Path,
    markdown_path: Path,
) -> tuple[str, list[str]]:
    """Converte o Markdown oficial do MinerU sem reconstruir junções de spans."""
    rendered = source_path.read_text(encoding="utf-8")
    missing_assets: list[str] = []
    table_markdown_by_html = _pdf_table_markdown_by_html(
        document,
        source_pdf_path,
    )
    corrupt_span_replacements = _pdf_corrupt_span_replacements(
        document,
        source_pdf_path,
    )
    inline_equation_replacements = _pdf_inline_equation_replacements(
        document,
        source_pdf_path,
    )

    for block in _iter_blocks(document):
        nodes = [block, *(span for line in block.lines for span in line.spans)]
        for node in nodes:
            corrupt_replacement = corrupt_span_replacements.get(node.id)
            if corrupt_replacement is not None:
                source_value = (
                    node.content
                    if node.content is not None
                    else node.text
                )
                if source_value not in rendered:
                    raise ValueError(
                        f"Span corrompido ausente no Markdown MinerU: {node.id}"
                    )
                rendered = rendered.replace(
                    source_value,
                    corrupt_replacement,
                )
            inline_equation_replacement = inline_equation_replacements.get(node.id)
            if inline_equation_replacement is not None:
                source_value = node.content if node.content is not None else node.text
                delimited_source = f"${source_value}$"
                if delimited_source not in rendered:
                    raise ValueError(
                        f"Equação inline ausente no Markdown MinerU: {node.id}"
                    )
                rendered = rendered.replace(
                    delimited_source,
                    inline_equation_replacement,
                )
                next_span = None
                for line in block.lines:
                    for span_index, candidate in enumerate(line.spans):
                        if candidate.id == node.id and span_index + 1 < len(line.spans):
                            next_span = line.spans[span_index + 1]
                            break
                    if next_span is not None:
                        break
                next_text = (
                    next_span.content or next_span.text or ""
                    if next_span is not None
                    else ""
                )
                if next_text.lstrip().startswith(":"):
                    rendered = rendered.replace(
                        inline_equation_replacement + " :",
                        inline_equation_replacement + ":",
                        1,
                    )
            if node.html is not None:
                converted = table_markdown_by_html.get(
                    node.html,
                    _html_to_markdown(node.html),
                )
                if node.html in rendered:
                    replacement = converted
                    if node.html.lstrip().lower().startswith("<table"):
                        replacement = "\n\n" + converted + "\n\n"
                    rendered = rendered.replace(node.html, replacement)
                elif converted not in rendered:
                    raise ValueError(
                        f"HTML do IR ausente no Markdown MinerU: {node.id}"
                    )
            for value in (node.content, node.text):
                if value is None:
                    continue
                converted = _text_or_html_to_markdown(value)
                if converted != value and value in rendered:
                    rendered = rendered.replace(value, converted)
            if node.image_path is None or node.html is not None:
                continue
            reference, missing_asset = _resolved_image_reference(
                node.image_path,
                middle_path=middle_path,
                markdown_path=markdown_path,
            )
            destinations = (
                f"]({node.image_path})",
                f"](images/{node.image_path})",
            )
            matched_destination = next(
                (
                    destination
                    for destination in destinations
                    if destination in rendered
                ),
                None,
            )
            if matched_destination is not None:
                rendered = rendered.replace(
                    matched_destination,
                    f"](<{reference}>)",
                )
            elif node.image_path in rendered:
                rendered = rendered.replace(node.image_path, reference)
            if missing_asset is not None:
                missing_assets.append(missing_asset)

    return (
        _repair_spacing_accents(
            _restore_missing_line_separators(document, rendered)
        ),
        list(dict.fromkeys(missing_assets)),
    )


def _include_source_furniture(
    document: DocumentIR,
    markdown: str,
    *,
    middle_path: Path,
    markdown_path: Path,
) -> tuple[str, list[str], list[str]]:
    """Reinsere headers/footers substantivos omitidos pelo Markdown MinerU."""
    headers: list[str] = []
    footers: list[str] = []
    included_ids: list[str] = []
    missing_assets: list[str] = []

    for page in document.pages:
        for block in page.discarded_blocks:
            if block.type not in {"header", "footer"}:
                continue
            content, block_missing_assets = _markdown_for_block(
                block,
                role="other",
                middle_path=middle_path,
                markdown_path=markdown_path,
            )
            if not content:
                continue
            included_ids.append(block.id)
            missing_assets.extend(block_missing_assets)
            if block.type == "header":
                headers.append(content)
            else:
                footers.append(content)

    parts = [*headers, markdown.rstrip("\n"), *footers]
    return (
        "\n\n".join(part for part in parts if part) + "\n",
        list(dict.fromkeys(missing_assets)),
        included_ids,
    )


def _ensure_semantic_heading(markdown: str) -> str:
    """Garante uma raiz hierárquica sem alterar nem duplicar texto extraído."""
    metadata_heading = re.compile(
        r"(?im)^(#{1,6})\s+((?:nome(?:\s+do\(a\)\s+aluno\(a\))?|aluno|"
        r"professor|data|n[uú]mero|t[ií]tulo\s+do\s+filme)\b.*)$"
    )
    normalized, demoted_count = metadata_heading.subn(r"\2", markdown)
    markdown = normalized
    if demoted_count:
        title_line = re.search(
            r"(?im)^(t[ií]tulo\s+(?:do\s+)?(?:t(?:i)?\s*2|trabalho)\s*:\s*.+)$",
            markdown,
        )
        if title_line is not None and not re.search(
            r"(?im)^#{1,6}\s+"
            + re.escape(title_line.group(1))
            + r"$",
            markdown,
        ):
            level = 2 if re.search(r"(?m)^#\s+\S", markdown) else 1
            start = title_line.start(1)
            markdown = markdown[:start] + "#" * level + " " + markdown[start:]
    if re.search(r"(?m)^\s{0,3}#{1,6}\s+\S", markdown):
        return markdown
    title_line = re.search(
        r"(?im)^(t[ií]tulo\s+(?:do\s+)?(?:t(?:i)?\s*2|trabalho)\s*:\s*.+)$",
        markdown,
    )
    if title_line is None:
        first_content = re.search(r"(?m)^(\S.*)$", markdown)
        if first_content is None:
            return markdown
        title_line = first_content
    start = title_line.start(1)
    return markdown[:start] + "# " + markdown[start:]


def _middle_paths(document_id: str) -> list[Path]:
    directory = settings.mineru_output_dir / "documents" / document_id
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.rglob("*_middle.json") if path.is_file() and path.stat().st_size
    )


def _existing_is_current(document_id: str, middle_path: Path) -> bool:
    ir_path = settings.ir_dir / document_id / "document_ir.json"
    structure_path = settings.structure_dir / document_id / "structure.json"
    markdown_path = settings.structure_dir / document_id / "document.md"
    render_path = settings.structure_dir / document_id / "render.json"
    if not all(
        path.is_file()
        for path in (ir_path, structure_path, markdown_path, render_path)
    ):
        return False
    try:
        ir = DocumentIR.model_validate_json(ir_path.read_text(encoding="utf-8"))
        render_metadata = json.loads(render_path.read_text(encoding="utf-8"))
        source_markdown = _mineru_markdown_path(middle_path)
        source_markdown_sha256 = (
            hashlib.sha256(source_markdown.read_bytes()).hexdigest()
            if source_markdown is not None
            else None
        )
        return (
            ir.middle_sha256
            == hashlib.sha256(middle_path.read_bytes()).hexdigest()
            and render_metadata.get("source_markdown_sha256")
            == source_markdown_sha256
            and not render_metadata.get("missing_assets")
        )
    except Exception:
        return False


def _render_one(row: dict[str, Any], overwrite: bool) -> dict[str, Any]:
    document_id = str(row["document_id"])
    middle_paths = _middle_paths(document_id)
    if not middle_paths:
        return {"document_id": document_id, "status": "pending", "reason": "middle.json ausente"}
    if len(middle_paths) != 1:
        return {
            "document_id": document_id,
            "status": "failed",
            "reason": f"middle.json ambíguo ({len(middle_paths)} encontrados)",
        }
    middle_path = middle_paths[0]
    if not overwrite and _existing_is_current(document_id, middle_path):
        return {"document_id": document_id, "status": "skipped", "middle_path": str(middle_path)}

    try:
        source_sha256 = str(row.get("sha256") or "")
        source_pdf_path = Path(str(row["path"])) if row.get("path") else None
        document = build_document_ir(
            middle_path,
            source_document_id=document_id,
            source_pdf_sha256=source_sha256 or None,
        )
        ir_validation = validate_document_ir(document, middle_path)
        if not ir_validation["valid"]:
            raise ValueError(f"IR inválido: {ir_validation['checks']}")

        structure = enrich_document(document)
        structure_validation = validate_structure(document, structure)
        if not structure_validation["valid"]:
            raise ValueError(f"Estrutura inválida: {structure_validation['checks']}")

        markdown_path = settings.structure_dir / document_id / "document.md"
        source_markdown_path = _mineru_markdown_path(middle_path)
        render_warnings: list[str] = []
        if source_markdown_path is not None:
            source_markdown_sha256 = hashlib.sha256(
                source_markdown_path.read_bytes()
            ).hexdigest()
            try:
                markdown, missing_assets = _render_mineru_markdown(
                    document,
                    source_path=source_markdown_path,
                    source_pdf_path=source_pdf_path,
                    middle_path=middle_path,
                    markdown_path=markdown_path,
                )
                render_source = "mineru_markdown"
            except ValueError as error:
                markdown, missing_assets = _render_markdown(
                    document,
                    structure,
                    middle_path=middle_path,
                    markdown_path=markdown_path,
                )
                render_source = "ir_reconstruction"
                render_warnings.append(
                    "Markdown MinerU incompatível com o middle.json; "
                    f"reconstrução pelo IR utilizada: {error}"
                )
        else:
            markdown, missing_assets = _render_markdown(
                document,
                structure,
                middle_path=middle_path,
                markdown_path=markdown_path,
            )
            render_source = "ir_reconstruction"
            source_markdown_sha256 = None
        markdown, furniture_missing_assets, included_discarded_ids = (
            _include_source_furniture(
                document,
                markdown,
                middle_path=middle_path,
                markdown_path=markdown_path,
            )
        )
        markdown = _ensure_semantic_heading(markdown)
        missing_assets = list(
            dict.fromkeys([*missing_assets, *furniture_missing_assets])
        )
        _atomic_write_text(
            settings.ir_dir / document_id / "document_ir.json",
            document.model_dump_json(exclude_none=True, indent=2) + "\n",
        )
        _atomic_write_json(
            settings.structure_dir / document_id / "structure.json",
            structure.model_dump(mode="json", exclude_none=True),
        )
        _atomic_write_text(markdown_path, markdown)
        status = "incomplete" if missing_assets else "ok"
        _atomic_write_json(
            settings.structure_dir / document_id / "render.json",
            {
                "document_id": document_id,
                "middle_sha256": document.middle_sha256,
                "source_pdf_sha256": document.source_pdf_sha256,
                "render_source": render_source,
                "source_markdown_sha256": source_markdown_sha256,
                "included_discarded_block_ids": included_discarded_ids,
                "status": status,
                "missing_assets": missing_assets,
                "warnings": render_warnings,
            },
        )
        return {
            "document_id": document_id,
            "status": status,
            "middle_path": str(middle_path),
            "render_source": render_source,
            "ir_validation": ir_validation,
            "structure_validation": structure_validation,
            "missing_assets": missing_assets,
            "warnings": render_warnings,
        }
    except JSONDecodeError as error:
        # Um middle.json ainda sendo gravado pode estar momentaneamente truncado.
        # JSON inválido e estável é tratado como falha na próxima execução.
        try:
            writing_window_seconds = 10
            age = datetime.now().timestamp() - middle_path.stat().st_mtime
            status = "pending" if age <= writing_window_seconds else "failed"
        except OSError:
            status = "pending"
        return {
            "document_id": document_id,
            "status": status,
            "middle_path": str(middle_path),
            "reason": f"JSONDecodeError: {error}",
        }
    except Exception as error:
        return {
            "document_id": document_id,
            "status": "failed",
            "middle_path": str(middle_path),
            "reason": f"{type(error).__name__}: {error}",
        }


def render(workers: int = 0, overwrite: bool = False) -> dict[str, Any]:
    """Gera IR, estrutura e Markdown para documentos ``ok`` do inventário.

    Erros de um documento são isolados no resumo; artefatos ausentes ficam
    ``pending`` para a próxima execução após a extração MinerU terminar.
    """
    if not settings.inventory_path.is_file():
        raise FileNotFoundError(f"Inventário ausente: {settings.inventory_path}")
    inventory = pd.read_csv(settings.inventory_path, dtype=str, keep_default_na=False)
    required = {"document_id", "status", "sha256"}
    missing_columns = required - set(inventory.columns)
    if missing_columns:
        raise ValueError(f"Inventário sem colunas obrigatórias: {sorted(missing_columns)}")
    rows = inventory.loc[inventory["status"].eq("ok")].to_dict("records")
    resolved_workers = workers or max(1, min(8, os.cpu_count() or 4))

    results: list[dict[str, Any] | None] = [None] * len(rows)
    with ThreadPoolExecutor(max_workers=resolved_workers) as executor:
        futures = {
            executor.submit(_render_one, row, overwrite): index
            for index, row in enumerate(rows)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                results[index] = future.result()
            except Exception as error:  # proteção adicional para o lote inteiro
                results[index] = {
                    "document_id": str(rows[index]["document_id"]),
                    "status": "failed",
                    "reason": f"{type(error).__name__}: {error}",
                }

    completed = [item for item in results if item is not None]
    summary = {
        "generated_at": _utc_now(),
        "inventory_path": str(settings.inventory_path),
        "workers": resolved_workers,
        "overwrite": overwrite,
        "counts": dict(sorted(Counter(item["status"] for item in completed).items())),
        "documents": completed,
    }
    summary_path = settings.structure_dir / "render_summary.json"
    _atomic_write_json(summary_path, summary)
    counts = ", ".join(
        f"{status}={count}" for status, count in summary["counts"].items()
    )
    print(f"Render concluído: {counts or 'nenhum documento'}")
    print(f"Resumo: {summary_path}")
    return summary
