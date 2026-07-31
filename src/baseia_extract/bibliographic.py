"""Extração conservadora de metadados bibliográficos canônicos."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .content_list import load_content_list_v2
from .ir.models import BlockIR, DocumentIR
from .metadata_overrides import DocumentMetadataOverride
from .semantic_models import BlockRole, DocumentStructure

_DOI_PATTERN = re.compile(
    r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+",
    re.IGNORECASE,
)
_YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")
_HTML_PATTERN = re.compile(r"<[^>]+>")
_SPACE_PATTERN = re.compile(r"\s+")
_ABSTRACT_HEADINGS = {
    "abstract": "en",
    "resumen": "es",
    "resumo": "pt",
}
_KEYWORD_PREFIXES = {
    "keywords": "en",
    "palabras clave": "es",
    "palavras-chave": "pt",
    "palavras chave": "pt",
}
_SECTION_STARTS = {
    "introducao",
    "introduction",
    "introduccion",
}
_AUTHOR_STOP_PATTERN = re.compile(
    r"(?i)\b(?:"
    r"doutor(?:a|ando|anda)?|mestre|mestrando|mestranda|"
    r"p[oó]s[- ]graduando|p[oó]s[- ]graduanda|graduando|graduanda|"
    r"instituicao|universidade|faculdade|endereco|e-?mail|orcid"
    r")\b"
)
_AUTHOR_REJECT_TERMS = {
    "approved",
    "brazilian",
    "curitiba",
    "doi",
    "issn",
    "journal",
    "recebido",
    "regras",
    "revista",
    "submitted",
    "versao",
    "volume",
}
_NAME_CONNECTORS = {"da", "das", "de", "do", "dos", "e"}


class BibliographicAuthor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    family_name: str
    provenance: str
    confidence: float = Field(ge=0, le=1)
    source_block_id: str | None = None


class BibliographicField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    provenance: str
    confidence: float = Field(ge=0, le=1)


class BibliographicMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    title: BibliographicField | None = None
    authors: list[BibliographicAuthor] = Field(default_factory=list)
    corporate_authors: list[BibliographicField] = Field(default_factory=list)
    doi: BibliographicField | None = None
    year: int | None = None
    year_provenance: str | None = None
    year_confidence: float | None = Field(default=None, ge=0, le=1)
    abstracts: dict[str, BibliographicField] = Field(default_factory=dict)
    keywords: dict[str, list[str]] = Field(default_factory=dict)
    citation_author: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


def _plain(value: str) -> str:
    without_html = _HTML_PATTERN.sub(" ", value)
    return _SPACE_PATTERN.sub(" ", without_html).strip()


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", _plain(value))
    ascii_value = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return _SPACE_PATTERN.sub(" ", ascii_value.casefold()).strip(" .:-")


def _block_text(block: BlockIR) -> str:
    values: list[str] = []
    for candidate in (block.text, block.content):
        if candidate:
            values.append(candidate)
    for line in block.lines:
        for span in line.spans:
            candidate = span.text or span.content
            if candidate:
                values.append(candidate)
    for child in block.blocks:
        child_text = _block_text(child)
        if child_text:
            values.append(child_text)
    return _plain(" ".join(values))


def _all_blocks(document: DocumentIR) -> Iterable[BlockIR]:
    def walk(block: BlockIR) -> Iterable[BlockIR]:
        yield block
        for child in block.blocks:
            yield from walk(child)

    for page in document.pages:
        for block in (*page.blocks, *page.discarded_blocks):
            yield from walk(block)


def _field(
    value: Any,
    provenance: str,
    confidence: float,
) -> BibliographicField | None:
    text = _plain(str(value)) if value is not None else ""
    if not text:
        return None
    return BibliographicField(
        value=text,
        provenance=provenance,
        confidence=confidence,
    )


def _metadata_attributes(document: DocumentIR) -> Mapping[str, Any]:
    nested = document.attributes.get("bibliographic_metadata")
    if isinstance(nested, Mapping):
        return nested
    return document.attributes


def _explicit_authors(document: DocumentIR) -> list[BibliographicAuthor]:
    attributes = _metadata_attributes(document)
    raw_authors = attributes.get("authors") or attributes.get("author") or []
    if isinstance(raw_authors, str):
        raw_authors = [raw_authors]
    if not isinstance(raw_authors, list):
        return []
    authors: list[BibliographicAuthor] = []
    for raw in raw_authors:
        value = (
            raw.get("full_name") or raw.get("name")
            if isinstance(raw, Mapping)
            else raw
        )
        name = _plain(str(value or ""))
        if not name:
            continue
        # Contrato deliberadamente simples aprovado para a primeira versão.
        family_name = name.split(" ")[-1]
        authors.append(
            BibliographicAuthor(
                full_name=name,
                family_name=family_name,
                provenance="document_ir.attributes",
                confidence=0.95,
            )
        )
    return authors


def _looks_like_person_name(value: str) -> str | None:
    candidate = _plain(value).strip(" ,;|-")
    candidate = _AUTHOR_STOP_PATTERN.split(candidate, maxsplit=1)[0].strip(
        " ,;|-"
    )
    normalized = _normalized(candidate)
    if (
        not candidate
        or ":" in candidate
        or "@" in candidate
        or any(character.isdigit() for character in candidate)
        or any(term in normalized.split() for term in _AUTHOR_REJECT_TERMS)
    ):
        return None
    tokens = candidate.split(" ")
    if not 2 <= len(tokens) <= 8:
        return None
    significant = [
        token
        for token in tokens
        if _normalized(token) not in _NAME_CONNECTORS
    ]
    if len(significant) < 2:
        return None
    valid_significant = sum(
        bool(token)
        and token[0].isalpha()
        and token[0].isupper()
        and all(
            character.isalpha() or character in {"'", "-", "."}
            for character in token
        )
        for token in significant
    )
    if valid_significant != len(significant):
        return None
    return candidate


def _authors_from_items(
    items: list[dict[str, Any]],
    *,
    title_order: int | None,
    front_matter_end: int | None,
) -> list[BibliographicAuthor]:
    start = -1 if title_order is None else title_order
    end = (
        start + 100
        if front_matter_end is None
        else front_matter_end
    )
    candidates: list[str] = []
    for item in items:
        order = int(item["global_order"])
        if (
            order <= start
            or order >= end
            or int(item["page_index"]) > 1
            or item.get("type") not in {"list", "paragraph"}
        ):
            continue
        for text_part in item.get("text_parts", []):
            if name := _looks_like_person_name(str(text_part)):
                candidates.append(name)
    unique: list[str] = []
    seen: set[str] = set()
    for name in candidates:
        key = _normalized(name)
        if key not in seen:
            seen.add(key)
            unique.append(name)
    return [
        BibliographicAuthor(
            full_name=name,
            family_name=name.split(" ")[-1],
            provenance="mineru.content_list_v2.front_matter",
            confidence=0.65,
        )
        for name in unique
    ]


def _authors_from_middle_front_matter(
    document: DocumentIR,
) -> list[BibliographicAuthor]:
    candidates: list[tuple[str, str]] = []
    document_title_seen = False
    front_matter_complete = False
    for page_index, page in enumerate(document.pages):
        if page_index > 1 or front_matter_complete:
            break
        for block in page.blocks:
            text = _block_text(block)
            normalized = _normalized(text)
            if block.type in {"title", "doc_title"}:
                if (
                    normalized in _ABSTRACT_HEADINGS
                    or normalized in _SECTION_STARTS
                ):
                    front_matter_complete = True
                    break
                if not document_title_seen:
                    document_title_seen = True
                continue
            if not document_title_seen:
                continue
            if block.type == "abstract":
                front_matter_complete = True
                break
            if block.type not in {"index", "list", "paragraph", "text"}:
                continue
            if name := _looks_like_person_name(text):
                candidates.append((name, block.id))

    authors: list[BibliographicAuthor] = []
    seen: set[str] = set()
    for name, block_id in candidates:
        key = _normalized(name)
        if key in seen:
            continue
        seen.add(key)
        authors.append(
            BibliographicAuthor(
                full_name=name,
                family_name=name.split(" ")[-1],
                provenance="mineru.middle_json.front_matter",
                confidence=0.6,
                source_block_id=block_id,
            )
        )
    return authors


def _citation_author(
    authors: list[BibliographicAuthor],
    corporate_authors: list[BibliographicField] | None = None,
) -> str | None:
    if not authors:
        return (
            corporate_authors[0].value
            if corporate_authors
            else None
        )
    if len(authors) == 1:
        return authors[0].family_name
    if len(authors) == 2:
        return (
            f"{authors[0].family_name} e "
            f"{authors[1].family_name}"
        )
    return f"{authors[0].family_name} et al."


def _keyword_payload(value: str) -> tuple[str, list[str]] | None:
    normalized = _normalized(value)
    for prefix, language in _KEYWORD_PREFIXES.items():
        if normalized.startswith(prefix):
            _, _, remainder = value.partition(":")
            keywords = [
                item.strip(" .")
                for item in remainder.split(",")
                if item.strip(" .")
            ]
            return language, keywords
    return None


def _abstracts_from_items(
    items: list[dict[str, Any]],
) -> tuple[dict[str, BibliographicField], dict[str, list[str]]]:
    abstracts: dict[str, BibliographicField] = {}
    keywords: dict[str, list[str]] = {}
    active_language: str | None = None
    parts: list[str] = []

    def flush() -> None:
        nonlocal parts
        if active_language and parts and active_language not in abstracts:
            abstracts[active_language] = BibliographicField(
                value=_plain(" ".join(parts)),
                provenance="mineru.content_list_v2",
                confidence=0.9,
            )
        parts = []

    for item in items:
        text = _plain(str(item.get("text") or ""))
        normalized = _normalized(text)
        if item.get("type") == "title":
            heading_language = _ABSTRACT_HEADINGS.get(normalized)
            if heading_language is not None:
                flush()
                active_language = heading_language
                continue
            if active_language is not None:
                flush()
                active_language = None
        if active_language is None or not text:
            continue
        if keyword_payload := _keyword_payload(text):
            language, values = keyword_payload
            keywords[language] = values
            flush()
            active_language = None
            continue
        if item.get("type") in {"paragraph", "list"}:
            parts.append(text)
    flush()
    return abstracts, keywords


def _title_from_items(
    items: list[dict[str, Any]],
) -> tuple[BibliographicField | None, int | None]:
    candidates = [
        item
        for item in items
        if item.get("type") == "title"
        and int(item["page_index"]) <= 1
        and _normalized(str(item.get("text") or ""))
        not in {
            *_ABSTRACT_HEADINGS,
            *_SECTION_STARTS,
            "referencias",
            "references",
        }
    ]
    preferred = next(
        (
            item
            for item in candidates
            if item.get("level") == 1 and int(item["page_index"]) == 0
        ),
        candidates[0] if candidates else None,
    )
    if preferred is None:
        return None, None
    return (
        _field(
            preferred.get("text"),
            "mineru.content_list_v2.title",
            0.9,
        ),
        int(preferred["global_order"]),
    )


def _front_matter_end(items: list[dict[str, Any]]) -> int | None:
    for item in items:
        if item.get("type") != "title":
            continue
        normalized = _normalized(str(item.get("text") or ""))
        if (
            normalized in _ABSTRACT_HEADINGS
            or normalized in _SECTION_STARTS
        ):
            return int(item["global_order"])
    return None


def derive_bibliographic_metadata(
    document: DocumentIR,
    structure: DocumentStructure | None = None,
    content_list_v2: str | Path | None = None,
    author_override: DocumentMetadataOverride | None = None,
) -> BibliographicMetadata:
    """Deriva somente valores sustentados pelos artefatos disponíveis."""
    loaded_items: list[dict[str, Any]] = []
    content_list_source: dict[str, Any] | None = None
    if content_list_v2 is not None:
        loaded = load_content_list_v2(content_list_v2)
        loaded_items = loaded["items"]
        content_list_source = loaded["source"]

    attributes = _metadata_attributes(document)
    explicit_title = _field(
        attributes.get("title"),
        "document_ir.attributes",
        0.95,
    )
    item_title, title_order = _title_from_items(loaded_items)
    title = explicit_title or item_title
    if title is None:
        title_block: BlockIR | None = None
        if structure is not None:
            blocks = {
                block.id: block for block in _all_blocks(document)
            }
            title_annotation = next(
                (
                    item
                    for item in structure.annotations
                    if item.role is BlockRole.TITLE
                ),
                None,
            )
            if title_annotation is not None:
                title_block = blocks.get(title_annotation.block_id)
        if title_block is None:
            title_block = next(
                (
                    block
                    for block in _all_blocks(document)
                    if block.type in {"title", "doc_title"}
                ),
                None,
            )
        if title_block is not None:
            title = _field(
                _block_text(title_block),
                "document_ir.title",
                0.7,
            )
    corporate_authors: list[BibliographicField] = []
    if author_override is not None:
        authors = [
            BibliographicAuthor(
                full_name=name,
                # Contrato deliberadamente simples aprovado para a primeira
                # versão: o último token é usado nas citações pessoais.
                family_name=name.split(" ")[-1],
                provenance=(
                    "manual_metadata_override."
                    f"{author_override.source}"
                ),
                confidence=1.0,
            )
            for name in author_override.authors
        ]
        corporate_authors = [
            BibliographicField(
                value=name,
                provenance=(
                    "manual_metadata_override."
                    f"{author_override.source}"
                ),
                confidence=1.0,
            )
            for name in author_override.corporate_authors
        ]
    else:
        authors = _explicit_authors(document)
        if not authors and loaded_items:
            authors = _authors_from_items(
                loaded_items,
                title_order=title_order,
                front_matter_end=_front_matter_end(loaded_items),
            )
        if not authors:
            authors = _authors_from_middle_front_matter(document)
    corpus = "\n".join(
        (
            str(item.get("text") or "")
            for item in loaded_items
            if int(item["page_index"]) <= 2
        )
    )
    if not corpus:
        corpus = "\n".join(
            _block_text(block) for block in _all_blocks(document)
        )
    doi_match = _DOI_PATTERN.search(corpus)
    doi = (
        _field(
            doi_match.group(0).rstrip(".,;"),
            (
                "mineru.content_list_v2"
                if loaded_items
                else "document_ir.text"
            ),
            0.85,
        )
        if doi_match
        else None
    )
    year_candidates = _YEAR_PATTERN.findall(corpus)
    year = None
    year_confidence = None
    if year_candidates:
        counts = Counter(year_candidates)
        selected, frequency = counts.most_common(1)[0]
        year = int(selected)
        year_confidence = min(0.8, 0.5 + 0.1 * (frequency - 1))

    abstracts, keywords = _abstracts_from_items(loaded_items)
    if not abstracts:
        for block in _all_blocks(document):
            if block.type == "abstract" and (text := _block_text(block)):
                abstracts.setdefault(
                    "und",
                    BibliographicField(
                        value=text,
                        provenance="document_ir.abstract",
                        confidence=0.8,
                    ),
                )

    author_review = (
        None
        if author_override is not None
        else
        {
            "status": "missing",
            "required": True,
            "reason": "not_identified_in_document_content",
            "candidate": [],
        }
        if not authors
        else {
            "status": "inferred",
            "required": True,
            "reason": "authors_inferred_from_front_matter",
            "provenance": sorted(
                {author.provenance for author in authors}
            ),
            "candidate": [
                author.model_dump(mode="json", exclude_none=True)
                for author in authors
            ],
        }
        if any(author.confidence < 0.8 for author in authors)
        else None
    )

    return BibliographicMetadata(
        title=title,
        authors=authors,
        corporate_authors=corporate_authors,
        doi=doi,
        year=year,
        year_provenance=(
            "mineru.content_list_v2"
            if year is not None and loaded_items
            else "document_ir.text"
            if year is not None
            else None
        ),
        year_confidence=year_confidence,
        abstracts=abstracts,
        keywords=keywords,
        citation_author=_citation_author(authors, corporate_authors),
        attributes={
            **(
                {"content_list_v2": content_list_source}
            if content_list_source is not None
            else {}
            ),
            **(
                {
                    "manual_metadata_override": {
                        "source": author_override.source,
                        "no_personal_author": (
                            author_override.no_personal_author
                        ),
                        "note": author_override.note,
                    }
                }
                if author_override is not None
                else {}
            ),
            **(
                {
                    "review": {
                        "authors": author_review,
                    }
                }
                if author_review is not None
                else {}
            ),
        },
    )


__all__ = [
    "BibliographicAuthor",
    "BibliographicField",
    "BibliographicMetadata",
    "derive_bibliographic_metadata",
]
