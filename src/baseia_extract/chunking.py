"""Projeção de DocumentIR + DocumentStructure em chunks para retrieval."""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import re
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .identity import canonical_json_sha256
from .ingest_models import BlockAction, IngestPolicy
from .ir.models import BlockIR, DocumentIR, SpanIR
from .semantic_models import BlockRole, DocumentStructure

CHUNKER_VERSION = 3

_ROLE_ASSET_KIND = {
    BlockRole.CHART: "chart",
    BlockRole.CODE: "code",
    BlockRole.EQUATION: "equation",
    BlockRole.FIGURE: "figure",
    BlockRole.TABLE: "table",
}
_TYPE_ASSET_KIND = {
    "chart": "chart",
    "code": "code",
    "equation": "equation",
    "image": "figure",
    "inline_equation": "equation",
    "interline_equation": "equation",
    "table": "table",
}
_DEFAULT_PLACEHOLDER = {
    "chart": "[GRÁFICO]",
    "code": "[CÓDIGO]",
    "equation": "[EQUAÇÃO]",
    "figure": "[FIGURA]",
    "table": "[TABELA]",
}


def _plain_html(value: str) -> str:
    return BeautifulSoup(value, "html.parser").get_text(
        " ",
        strip=True,
    )


def _node_text(value: Any) -> str:
    text = getattr(value, "text", None) or getattr(value, "content", None)
    if text:
        return _plain_html(text) if "<" in text and ">" in text else text
    html = getattr(value, "html", None)
    if html:
        return _plain_html(html)
    return ""


def _block_text(block: BlockIR) -> str:
    if block.lines:
        lines: list[str] = []
        for line in block.lines:
            spans: list[str] = []
            for span in line.spans:
                if span.type in {
                    "inline_equation",
                    "interline_equation",
                } or span.latex:
                    spans.append("[EQUAÇÃO]")
                elif span.image_path:
                    spans.append("[FIGURA]")
                else:
                    spans.append(_node_text(span))
            lines.append("".join(spans))
        content = "\n".join(lines)
    else:
        content = _node_text(block)
    children = [
        _block_text(child)
        for child in block.blocks
        if child.type not in _TYPE_ASSET_KIND
    ]
    return "\n\n".join(
        part.strip()
        for part in (content, *children)
        if part and part.strip()
    )


def _caption_text(block: BlockIR) -> str:
    captions: list[str] = []

    def visit(node: BlockIR) -> None:
        if node is not block and node.type and (
            "caption" in node.type or "title" in node.type
        ):
            value = _block_text(node)
            if value:
                captions.append(value)
        for child in node.blocks:
            visit(child)

    visit(block)
    if captions:
        return re.sub(r"\s+", " ", " ".join(captions)).strip()
    values = [
        _node_text(span)
        for line in block.lines
        for span in line.spans
        if not span.image_path
        and not span.latex
        and span.type not in {"inline_equation", "interline_equation"}
    ]
    return re.sub(r"\s+", " ", " ".join(values)).strip()


def _resolve_asset_path(
    declared: str,
    *,
    asset_root: Path,
) -> Path | None:
    relative = Path(declared)
    candidates = [
        relative if relative.is_absolute() else asset_root / relative,
        asset_root / "images" / relative.name,
        asset_root / relative.name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    matches = sorted(
        path
        for path in asset_root.rglob(relative.name)
        if path.is_file()
    )
    return matches[0].resolve() if matches else None


def _asset_payload(
    *,
    revision_id: str,
    block_id: str,
    node: Any,
    kind: str,
    page: int,
    caption: str,
    asset_root: Path,
    include_base64: bool,
) -> dict[str, Any]:
    node_id = str(getattr(node, "id", block_id))
    asset_id = str(
        uuid.uuid5(
            _revision_namespace(revision_id),
            f"asset:{node_id}:{kind}",
        )
    )
    payload: dict[str, Any] = {
        "asset_id": asset_id,
        "kind": kind,
        "block_id": block_id,
        "node_id": node_id,
        "page": page,
        "caption": caption or None,
    }
    html = getattr(node, "html", None)
    latex = getattr(node, "latex", None)
    if html:
        payload["html"] = html
    if latex:
        payload["latex"] = latex
    declared_path = getattr(node, "image_path", None)
    if declared_path:
        resolved = _resolve_asset_path(
            str(declared_path),
            asset_root=asset_root,
        )
        payload["source_filename"] = Path(str(declared_path)).name
        if resolved is None:
            payload["missing"] = True
        else:
            raw = resolved.read_bytes()
            payload.update(
                mime_type=(
                    mimetypes.guess_type(resolved.name)[0]
                    or "application/octet-stream"
                ),
                sha256=hashlib.sha256(raw).hexdigest(),
                bytes=len(raw),
            )
            try:
                payload["source_relative_path"] = resolved.relative_to(
                    asset_root.resolve()
                ).as_posix()
            except ValueError:
                payload["source_relative_path"] = resolved.name
            if include_base64:
                payload["data_base64"] = base64.b64encode(raw).decode(
                    "ascii"
                )
    return {key: value for key, value in payload.items() if value is not None}


def _walk_asset_nodes(block: BlockIR) -> list[tuple[Any, str]]:
    nodes: list[tuple[Any, str]] = []

    def add_node(node: Any, fallback_kind: str | None = None) -> None:
        node_type = str(getattr(node, "type", "") or "")
        kind = _TYPE_ASSET_KIND.get(node_type, fallback_kind)
        if (
            kind is not None
            and (
                getattr(node, "image_path", None)
                or getattr(node, "html", None)
                or getattr(node, "latex", None)
                or node_type in _TYPE_ASSET_KIND
            )
        ):
            nodes.append((node, kind))

    add_node(block, _TYPE_ASSET_KIND.get(str(block.type or "")))
    for line in block.lines:
        for span in line.spans:
            add_node(span)
    for child in block.blocks:
        nodes.extend(_walk_asset_nodes(child))
    return nodes


def _assets_for_block(
    *,
    revision_id: str,
    block: BlockIR,
    role: BlockRole,
    page: int,
    asset_root: Path,
    include_base64: bool,
) -> list[dict[str, Any]]:
    caption = _caption_text(block)
    nodes = _walk_asset_nodes(block)
    expected_kind = _ROLE_ASSET_KIND.get(role)
    if expected_kind is not None and not nodes:
        nodes = [(block, expected_kind)]
    assets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node, inferred_kind in nodes:
        kind = expected_kind or inferred_kind
        payload = _asset_payload(
            revision_id=revision_id,
            block_id=block.id,
            node=node,
            kind=kind,
            page=page,
            caption=caption,
            asset_root=asset_root,
            include_base64=include_base64,
        )
        asset_id = str(payload["asset_id"])
        if asset_id not in seen:
            seen.add(asset_id)
            assets.append(payload)
    material_keys = {
        "source_filename",
        "html",
        "latex",
        "data_base64",
        "missing",
    }
    material_kinds = {
        str(asset["kind"])
        for asset in assets
        if material_keys.intersection(asset)
    }
    return [
        asset
        for asset in assets
        if (
            str(asset["kind"]) not in material_kinds
            or bool(material_keys.intersection(asset))
        )
    ]


def _placeholder(
    policy: IngestPolicy,
    role: BlockRole,
    caption: str,
) -> str:
    rule = policy.blocks[role]
    kind = _ROLE_ASSET_KIND.get(role, role.value)
    label = rule.placeholder or _DEFAULT_PLACEHOLDER.get(
        kind,
        f"[{kind.upper()}]",
    )
    return f"{label} {caption}".strip()


def _title_text(block: BlockIR) -> str:
    return re.sub(r"\s+", " ", _block_text(block)).strip()


def _section_paths(
    structure: DocumentStructure,
    blocks: dict[str, BlockIR],
) -> dict[str, list[str]]:
    sections = {section.id: section for section in structure.sections}
    paths: dict[str, list[str]] = {}
    for section in structure.sections:
        values: list[str] = []
        current = section
        visited: set[str] = set()
        while current.id not in visited:
            visited.add(current.id)
            if current.title_block_id:
                title = blocks.get(current.title_block_id)
                if title is not None and (value := _title_text(title)):
                    values.append(value)
            if current.parent_id is None:
                break
            parent = sections.get(current.parent_id)
            if parent is None:
                break
            current = parent
        paths[section.id] = list(reversed(values))
    return paths


def _compact_bibliographic(
    metadata: dict[str, Any],
    policy: IngestPolicy,
) -> dict[str, Any]:
    keys = [
        "authors",
        "corporate_authors",
        "doi",
        "year",
        "citation_author",
    ]
    if policy.include_title_payload:
        keys.insert(0, "title")
    return {
        key: metadata[key]
        for key in keys
        if metadata.get(key) not in (None, [], {}, "")
    }


def _document_bibliographic_payload(
    metadata: dict[str, Any],
    policy: IngestPolicy,
) -> dict[str, Any]:
    payload = dict(metadata)
    if not policy.include_title_payload:
        payload.pop("title", None)
    if not policy.include_abstract_payload:
        payload.pop("abstracts", None)
        payload.pop("keywords", None)
    return payload


def _include_payload_block(
    role: BlockRole,
    policy: IngestPolicy,
) -> bool:
    if role is BlockRole.TITLE:
        return policy.include_title_payload
    if role is BlockRole.ABSTRACT:
        return policy.include_abstract_payload
    if role is BlockRole.REFERENCE:
        return policy.include_references_payload
    return True


def _metadata_title(metadata: dict[str, Any]) -> str:
    title = metadata.get("title")
    if isinstance(title, dict):
        return str(title.get("value") or "").strip()
    return str(title or "").strip()


def _revision_namespace(revision_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(revision_id))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"baseia:{revision_id}")


def _payload_block(
    block: BlockIR,
    *,
    role: BlockRole,
    page: int,
    section_id: str | None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "block_id": block.id,
        "role": role.value,
        "page": page,
        "section_id": section_id,
        "text": _block_text(block) or None,
        "html": block.html,
        "latex": block.latex,
    }
    return {key: item for key, item in value.items() if item is not None}


def _contextual_text(
    body: str,
    *,
    policy: IngestPolicy,
    title: str,
    heading_path: list[str],
) -> str:
    if not policy.contextual_prefix:
        return body
    context: list[str] = []
    if title:
        context.append(f"Documento: {title}")
    if heading_path:
        context.append(f"Seção: {' > '.join(heading_path)}")
    return "\n".join([*context, "", body]).strip()


def build_chunks(
    *,
    revision_id: str,
    document: DocumentIR,
    structure: DocumentStructure,
    policy: IngestPolicy,
    metadata: dict[str, Any] | None = None,
    markdown_path: Path | None = None,
    asset_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Produz chunks determinísticos sem reconstruir estrutura do Markdown."""
    metadata = dict(metadata or {})
    resolved_asset_root = (
        asset_root.resolve()
        if asset_root is not None
        else Path(document.source_path).resolve().parent
    )
    blocks = {
        block.id: block for page in document.pages for block in page.blocks
    }
    annotations = {
        annotation.block_id: annotation
        for annotation in structure.annotations
    }
    section_paths = _section_paths(structure, blocks)
    policy_payload = policy.model_dump(mode="json")
    policy_hash = canonical_json_sha256(policy_payload)
    title = _metadata_title(metadata)
    compact_bibliographic = _compact_bibliographic(metadata, policy)

    payload_only: list[dict[str, Any]] = []
    units_by_section: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for block_id in structure.primary_flow_block_ids:
        block = blocks.get(block_id)
        annotation = annotations.get(block_id)
        if block is None or annotation is None:
            continue
        rule = policy.blocks.get(annotation.role)
        if rule is None:
            rule = policy.blocks[BlockRole.OTHER]
        if rule.action is BlockAction.EXCLUDE:
            continue
        if rule.action is BlockAction.PAYLOAD:
            if _include_payload_block(annotation.role, policy):
                payload_only.append(
                    _payload_block(
                        block,
                        role=annotation.role,
                        page=annotation.page,
                        section_id=annotation.section_id,
                    )
                )
            continue

        assets = _assets_for_block(
            revision_id=revision_id,
            block=block,
            role=annotation.role,
            page=annotation.page,
            asset_root=resolved_asset_root,
            include_base64=policy.base64_assets,
        )
        if rule.action is BlockAction.PLACEHOLDER:
            text = _placeholder(
                policy,
                annotation.role,
                _caption_text(block),
            )
        else:
            text = _block_text(block)
            inline_placeholders = [
                _DEFAULT_PLACEHOLDER.get(
                    str(asset["kind"]),
                    f"[{str(asset['kind']).upper()}]",
                )
                for asset in assets
                if str(asset["kind"]) in {"equation", "figure", "table"}
            ]
            if inline_placeholders and not any(
                placeholder in text for placeholder in inline_placeholders
            ):
                text = "\n".join([text, *inline_placeholders]).strip()
        if not text.strip():
            continue
        section_id = annotation.section_id or structure.root_section_id
        units_by_section[section_id].append(
            {
                "block_id": block.id,
                "page": annotation.page,
                "role": annotation.role.value,
                "text": text.strip(),
                "assets": assets,
            }
        )

    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=policy.splitter.tokenizer.value,
        chunk_size=policy.splitter.chunk_size,
        chunk_overlap=policy.splitter.chunk_overlap,
        add_start_index=True,
        separators=["\n\n", "\n", ". ", " ", ""],
        keep_separator=True,
    )
    pending: list[dict[str, Any]] = []
    for section_ordinal, section in enumerate(structure.sections):
        units = units_by_section.get(section.id, [])
        if not units:
            continue
        parts: list[str] = []
        cursor = 0
        ranges: list[dict[str, Any]] = []
        for unit in units:
            if parts:
                parts.append("\n\n")
                cursor += 2
            start = cursor
            parts.append(unit["text"])
            cursor += len(unit["text"])
            ranges.append({**unit, "start": start, "end": cursor})
        parent_text = "".join(parts)
        documents = splitter.create_documents(
            [parent_text],
            [{"section_id": section.id}],
        )
        for section_chunk_index, child in enumerate(documents):
            start = int(child.metadata.get("start_index", 0))
            end = start + len(child.page_content)
            intersecting = [
                unit
                for unit in ranges
                if unit["end"] > start and unit["start"] < end
            ]
            if not intersecting:
                continue
            asset_ids = list(
                dict.fromkeys(
                    str(asset["asset_id"])
                    for unit in intersecting
                    for asset in unit["assets"]
                )
            )
            pending.append(
                {
                    "section_id": section.id,
                    "section_ordinal": section_ordinal,
                    "section_chunk_index": section_chunk_index,
                    "content_text": child.page_content,
                    "heading_path": section_paths.get(section.id, []),
                    "block_ids": list(
                        dict.fromkeys(
                            str(unit["block_id"])
                            for unit in intersecting
                        )
                    ),
                    "pages": sorted(
                        {
                            int(unit["page"])
                            for unit in intersecting
                        }
                    ),
                    "roles": list(
                        dict.fromkeys(
                            str(unit["role"])
                            for unit in intersecting
                        )
                    ),
                    "asset_ids": asset_ids,
                    "_assets": [
                        asset
                        for unit in intersecting
                        for asset in unit["assets"]
                    ],
                }
            )

    markdown = (
        markdown_path.read_text(encoding="utf-8")
        if markdown_path is not None and markdown_path.is_file()
        else None
    )
    namespace = _revision_namespace(revision_id)
    output: list[dict[str, Any]] = []
    for chunk_index, chunk in enumerate(pending):
        content_text = str(chunk.pop("content_text"))
        chunk_assets: list[dict[str, Any]] = []
        seen_assets: set[str] = set()
        for asset in chunk.pop("_assets"):
            asset_id = str(asset["asset_id"])
            if asset_id not in seen_assets:
                seen_assets.add(asset_id)
                chunk_assets.append(asset)
        embedding_text = _contextual_text(
            content_text,
            policy=policy,
            title=title,
            heading_path=list(chunk["heading_path"]),
        )
        text_sha256 = hashlib.sha256(
            embedding_text.encode("utf-8")
        ).hexdigest()
        chunk_id = str(
            uuid.uuid5(
                namespace,
                (
                    f"chunk:{policy_hash}:{chunk_index}:"
                    f"{text_sha256}"
                ),
            )
        )
        parent_id = str(
            uuid.uuid5(
                namespace,
                f"parent:{policy_hash}:{chunk['section_id']}",
            )
        )
        result: dict[str, Any] = {
            "schema_version": 1,
            "chunker_version": CHUNKER_VERSION,
            "chunk_id": chunk_id,
            "parent_id": parent_id,
            "document_id": document.id,
            "revision_id": revision_id,
            "chunk_index": chunk_index,
            "section_chunk_index": chunk["section_chunk_index"],
            "section_id": chunk["section_id"],
            "heading_path": chunk["heading_path"],
            "block_ids": chunk["block_ids"],
            "pages": chunk["pages"],
            "roles": chunk["roles"],
            "text": embedding_text,
            "content_text": content_text,
            "text_sha256": text_sha256,
            "policy": {
                "name": policy.name,
                "hash": policy_hash,
                "contextual_prefix": policy.contextual_prefix,
            },
            "bibliographic": compact_bibliographic,
            "asset_ids": chunk["asset_ids"],
            "assets": chunk_assets,
        }
        if chunk_index == 0:
            result["document_payload"] = {
                "bibliographic": _document_bibliographic_payload(
                    metadata,
                    policy,
                ),
                "non_embedded_blocks": payload_only,
                "canonical_markdown": markdown,
            }
        output.append(result)
    return output


__all__ = ["CHUNKER_VERSION", "build_chunks"]
