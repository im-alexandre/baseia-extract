"""Enriquecimento estrutural determinístico para o IR canônico."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

from baseia_extract.ir.models import BlockIR, DocumentIR, PageIR
from baseia_extract.semantic_models import (
    AssetKind,
    AssetRef,
    BlockAnnotation,
    BlockRole,
    DocumentStructure,
    ListGroup,
    SectionNode,
)

ROLE_BY_BLOCK_TYPE: dict[str, BlockRole] = {
    "abstract": BlockRole.ABSTRACT,
    "algorithm": BlockRole.CODE,
    "aside_text": BlockRole.ASIDE,
    "author": BlockRole.METADATA,
    "authors": BlockRole.METADATA,
    "chart": BlockRole.CHART,
    "code": BlockRole.CODE,
    "date": BlockRole.METADATA,
    "doi": BlockRole.METADATA,
    "image": BlockRole.FIGURE,
    "index": BlockRole.LIST,
    "interline_equation": BlockRole.EQUATION,
    "list": BlockRole.LIST,
    "page_footnote": BlockRole.ASIDE,
    "ref_text": BlockRole.REFERENCE,
    "table": BlockRole.TABLE,
    "text": BlockRole.BODY,
    "title": BlockRole.TITLE,
}

ROLE_BY_CONTENT_LIST_TYPE: dict[str, BlockRole] = {
    "algorithm": BlockRole.CODE,
    "chart": BlockRole.CHART,
    "code": BlockRole.CODE,
    "equation_interline": BlockRole.EQUATION,
    "image": BlockRole.FIGURE,
    "index": BlockRole.LIST,
    "list": BlockRole.LIST,
    "page_aside_text": BlockRole.ASIDE,
    "page_footnote": BlockRole.ASIDE,
    "paragraph": BlockRole.BODY,
    "table": BlockRole.TABLE,
    "title": BlockRole.TITLE,
}

EXCLUDED_PRIMARY_TYPES = frozenset({"header", "footer", "page_number"})

ASSET_KIND_BY_ROLE: dict[BlockRole, AssetKind] = {
    BlockRole.FIGURE: AssetKind.FIGURE,
    BlockRole.TABLE: AssetKind.TABLE,
    BlockRole.CHART: AssetKind.CHART,
    BlockRole.EQUATION: AssetKind.EQUATION,
    BlockRole.CODE: AssetKind.CODE,
}

_REFERENCE_HEADINGS = {
    "bibliografia",
    "bibliography",
    "referencias",
    "referencias bibliograficas",
    "references",
}
_ABSTRACT_HEADINGS = {"abstract", "resumen", "resumo"}
_INTRODUCTION_HEADINGS = {
    "introducao",
    "introduction",
    "introduccion",
}
_METADATA_MARKERS = re.compile(
    r"(?i)\b(?:doi|e-?mail|orcid|institui[cç][aã]o|universidade|"
    r"faculdade|submitted|approved|recebido|aceito|vers[aã]o|"
    r"doutor(?:a|ando|anda)?|mestre|p[oó]s[- ]graduando)\b"
)
_NAME_CONNECTORS = {"da", "das", "de", "do", "dos", "e"}


def _section_id(document_id: str, title_block_id: str) -> str:
    return f"{document_id}:section:{title_block_id}"


def _list_group_id(document_id: str, first_block_id: str) -> str:
    return f"{document_id}:list:{first_block_id}"


def _asset_id(document_id: str, block_id: str) -> str:
    return f"{document_id}:asset:{block_id}"


def _iter_content_blocks(
    document: DocumentIR,
) -> Iterable[tuple[PageIR, BlockIR]]:
    for page in document.pages:
        for block in page.blocks:
            yield page, block


def _iter_discarded_blocks(
    document: DocumentIR,
) -> Iterable[tuple[PageIR, BlockIR]]:
    for page in document.pages:
        for block in page.discarded_blocks:
            yield page, block


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    ascii_value = re.sub(r"<[^>]+>", " ", ascii_value)
    return re.sub(r"\s+", " ", ascii_value.casefold()).strip(" .:-")


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
    return re.sub(r"\s+", " ", " ".join(values)).strip()


def _match_map(
    reconciliation: Mapping[str, Any] | None,
    *,
    usable_only: bool = False,
) -> dict[str, dict[str, Any]]:
    if reconciliation is None:
        return {}
    if (
        usable_only
        and reconciliation.get("page_count_matches_ir") is not True
    ):
        return {}
    matches = reconciliation.get("matches", [])
    if not isinstance(matches, list):
        return {}
    return {
        str(item["block_id"]): dict(item)
        for item in matches
        if (
            isinstance(item, Mapping)
            and item.get("block_id")
            and (
                not usable_only
                or item.get("usable_for_structure") is True
            )
        )
    }


def _ordered_content_blocks(
    document: DocumentIR,
    matches: Mapping[str, Mapping[str, Any]],
) -> list[tuple[PageIR, BlockIR]]:
    """Mescla a ordem v2 dos associados com fallback físico dos demais."""
    result: list[tuple[PageIR, BlockIR]] = []
    for page in document.pages:
        physical = list(page.blocks)
        physical_index = {
            block.id: index for index, block in enumerate(physical)
        }
        matched_ids = [
            block.id
            for block in physical
            if block.id in matches
            and matches[block.id].get("source_kind") == "content"
        ]
        preferred = sorted(
            matched_ids,
            key=lambda block_id: (
                int(matches[block_id].get("ordinal", 0)),
                physical_index[block_id],
            ),
        )
        if not preferred:
            result.extend((page, block) for block in physical)
            continue

        preferred_set = set(preferred)
        before: dict[str, list[BlockIR]] = {
            block_id: [] for block_id in preferred
        }
        tail: list[BlockIR] = []
        for index, block in enumerate(physical):
            if block.id in preferred_set:
                continue
            next_matched = next(
                (
                    candidate.id
                    for candidate in physical[index + 1 :]
                    if candidate.id in preferred_set
                ),
                None,
            )
            if next_matched is None:
                tail.append(block)
            else:
                before[next_matched].append(block)
        blocks_by_id = {block.id: block for block in physical}
        for block_id in preferred:
            result.extend((page, block) for block in before[block_id])
            result.append((page, blocks_by_id[block_id]))
        result.extend((page, block) for block in tail)
    return result


def _classify_role(
    block: BlockIR,
    match: Mapping[str, Any] | None,
) -> BlockRole:
    if match is not None and match.get("compatible_type") is True:
        source_type = match.get("source_type")
        if isinstance(source_type, str):
            role = ROLE_BY_CONTENT_LIST_TYPE.get(source_type)
            if role is not None:
                return role
    if block.type is None:
        return BlockRole.OTHER
    return ROLE_BY_BLOCK_TYPE.get(block.type, BlockRole.OTHER)


def _title_level(
    block: BlockIR,
    match: Mapping[str, Any] | None,
) -> int:
    if match is not None:
        value = match.get("level")
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 1
        ):
            return value
    return block.level if block.level is not None and block.level >= 1 else 1


def _block_has_content(block: BlockIR) -> bool:
    return bool(
        block.text
        or block.content
        or block.lines
        or block.html
        or block.latex
        or block.image_path
        or block.blocks
    )


def _looks_like_name(value: str) -> bool:
    if not value or ":" in value or "@" in value:
        return False
    tokens = value.split()
    if not 2 <= len(tokens) <= 8:
        return False
    significant = [
        token
        for token in tokens
        if _normalized(token) not in _NAME_CONNECTORS
    ]
    return len(significant) >= 2 and all(
        token[0].isupper()
        and all(
            character.isalpha() or character in {"'", "-", "."}
            for character in token
        )
        for token in significant
        if token
    )


def _looks_bibliographic_metadata(block: BlockIR) -> bool:
    text = _block_text(block)
    return bool(
        text
        and (
            _METADATA_MARKERS.search(text)
            or _looks_like_name(text)
        )
    )


def _reconciliation_summary(
    reconciliation: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if reconciliation is None:
        return None
    return {
        key: reconciliation[key]
        for key in (
            "schema_version",
            "reconciler_version",
            "source",
            "page_count_matches_ir",
            "counts",
            "confidence",
            "unmatched_items",
            "unmatched_blocks",
        )
        if key in reconciliation
    }


def enrich_document(
    document: DocumentIR,
    *,
    content_list_v2: Mapping[str, Any] | None = None,
) -> DocumentStructure:
    """Deriva ordem, seções, papéis e assets sem modificar o IR.

    Quando o v2 está disponível, sua ordem e seus tipos são evidência
    preferencial. Blocos não associados permanecem no fluxo por fallback
    físico e a divergência fica explícita nos atributos.
    """
    evidence_matches = _match_map(content_list_v2)
    structure_matches = _match_map(
        content_list_v2,
        usable_only=True,
    )
    ordered_pairs = _ordered_content_blocks(document, structure_matches)
    root_section_id = f"{document.id}:section-root"
    root = SectionNode(id=root_section_id, level=0, ordinal=0)
    sections = [root]
    section_stack = [root]
    annotations: list[BlockAnnotation] = []
    list_groups: list[ListGroup] = []
    assets: list[AssetRef] = []
    primary_flow_block_ids: list[str] = []
    active_list_group: ListGroup | None = None
    reference_level: int | None = None
    abstract_level: int | None = None
    document_title_seen = False
    first_section_seen = False

    for reading_order, (page, block) in enumerate(ordered_pairs):
        match = evidence_matches.get(block.id)
        decision_match = structure_matches.get(block.id)
        role = _classify_role(block, decision_match)
        excluded = block.type in EXCLUDED_PRIMARY_TYPES
        text_heading = _normalized(_block_text(block))

        if role is BlockRole.TITLE:
            level = _title_level(block, decision_match)
            if reference_level is not None and level <= reference_level:
                reference_level = None
            if abstract_level is not None and level <= abstract_level:
                abstract_level = None
            if text_heading in _REFERENCE_HEADINGS:
                reference_level = level
                first_section_seen = True
            elif text_heading in _ABSTRACT_HEADINGS:
                abstract_level = level
                first_section_seen = True
            elif (
                text_heading in _INTRODUCTION_HEADINGS
                or (
                    document_title_seen
                    and (
                        page.page > 0
                        or re.match(r"^\d+(?:[.\s]|$)", text_heading)
                        is not None
                    )
                )
            ):
                first_section_seen = True

            while (
                len(section_stack) > 1
                and section_stack[-1].level >= level
            ):
                section_stack.pop()
            parent = section_stack[-1]
            section = SectionNode(
                id=_section_id(document.id, block.id),
                parent_id=parent.id,
                title_block_id=block.id,
                level=level,
                ordinal=len(sections),
                block_ids=[block.id],
            )
            parent.child_ids.append(section.id)
            sections.append(section)
            section_stack.append(section)
            if not document_title_seen:
                document_title_seen = True
        else:
            section = section_stack[-1]
            section.block_ids.append(block.id)
            if reference_level is not None:
                role = BlockRole.REFERENCE
            elif abstract_level is not None:
                role = BlockRole.ABSTRACT
            elif (
                document_title_seen
                and not first_section_seen
                and page.page <= 1
                and role in {BlockRole.BODY, BlockRole.LIST}
                and _looks_bibliographic_metadata(block)
            ):
                role = BlockRole.METADATA

        if role is BlockRole.LIST:
            if (
                active_list_group is None
                or active_list_group.section_id != section.id
            ):
                active_list_group = ListGroup(
                    id=_list_group_id(document.id, block.id),
                    section_id=section.id,
                )
                list_groups.append(active_list_group)
            active_list_group.block_ids.append(block.id)
            list_group_id: str | None = active_list_group.id
        else:
            active_list_group = None
            list_group_id = None

        content_list_attributes: dict[str, Any]
        if match is None:
            content_list_attributes = {
                "matched": False,
                "order_source": "middle_json_fallback",
            }
        else:
            content_list_attributes = {
                "matched": True,
                "applied_to_structure": decision_match is not None,
                "order_source": (
                    "content_list_v2"
                    if decision_match is not None
                    else "middle_json_fallback"
                ),
                **{
                    key: match[key]
                    for key in (
                        "item_id",
                        "page_index",
                        "ordinal",
                        "global_order",
                        "source_type",
                        "level",
                        "confidence",
                        "confidence_label",
                        "score_margin",
                        "ambiguous",
                        "usable_for_structure",
                        "bbox_coordinate_space",
                        "bbox_iou",
                        "text_similarity",
                        "compatible_type",
                        "divergences",
                    )
                    if key in match
                },
            }
        annotations.append(
            BlockAnnotation(
                block_id=block.id,
                page_id=page.id,
                page=page.page,
                reading_order=reading_order,
                role=role,
                source_type=block.type,
                section_id=section.id,
                list_group_id=list_group_id,
                excluded_from_primary_flow=excluded,
                attributes={
                    "has_content": _block_has_content(block),
                    "cross_page": block.cross_page,
                    "content_list_v2": content_list_attributes,
                },
            )
        )

        if not excluded:
            primary_flow_block_ids.append(block.id)

        asset_kind = ASSET_KIND_BY_ROLE.get(role)
        if asset_kind is not None:
            assets.append(
                AssetRef(
                    id=_asset_id(document.id, block.id),
                    block_id=block.id,
                    page_id=page.id,
                    page=page.page,
                    kind=asset_kind,
                    section_id=section.id,
                )
            )

    attributes: dict[str, Any] = {
        "backend": document.backend,
        "backend_version": document.backend_version,
        "reading_order_source": (
            "middle_json"
            if content_list_v2 is None
            else "content_list_v2_rejected_page_count_mismatch"
            if content_list_v2.get("page_count_matches_ir") is not True
            else "content_list_v2_with_middle_fallback"
        ),
    }
    reconciliation_summary = _reconciliation_summary(content_list_v2)
    if reconciliation_summary is not None:
        attributes["content_list_v2"] = reconciliation_summary
    return DocumentStructure(
        document_id=document.id,
        middle_sha256=document.middle_sha256,
        source_pdf_sha256=document.source_pdf_sha256,
        root_section_id=root_section_id,
        sections=sections,
        annotations=annotations,
        list_groups=list_groups,
        assets=assets,
        primary_flow_block_ids=primary_flow_block_ids,
        discarded_block_ids=[
            block.id for _, block in _iter_discarded_blocks(document)
        ],
        attributes=attributes,
    )


def validate_structure(
    document: DocumentIR,
    structure: DocumentStructure,
) -> dict[str, Any]:
    """Valida cobertura, referências e serialização sem reprocessar conteúdo."""
    content_pairs = list(_iter_content_blocks(document))
    content_block_ids = [block.id for _, block in content_pairs]
    discarded_block_ids = [
        block.id for _, block in _iter_discarded_blocks(document)
    ]
    annotations = structure.annotations
    annotation_ids = [item.block_id for item in annotations]
    sections_by_id = {
        section.id: section for section in structure.sections
    }
    group_ids = {group.id for group in structure.list_groups}
    expected_asset_ids = {
        annotation.block_id
        for annotation in annotations
        if annotation.role in ASSET_KIND_BY_ROLE
    }
    actual_asset_ids = {asset.block_id for asset in structure.assets}

    expected_page_by_block = {
        block.id: page for page, block in content_pairs
    }
    annotations_match_pages = all(
        (page := expected_page_by_block.get(annotation.block_id)) is not None
        and annotation.page_id == page.id
        and annotation.page == page.page
        for annotation in annotations
    )
    valid_section_edges = all(
        section.parent_id is None
        or section.parent_id in sections_by_id
        for section in structure.sections
    ) and all(
        child_id in sections_by_id
        for section in structure.sections
        for child_id in section.child_ids
    )
    list_memberships_match = all(
        annotation.list_group_id is None
        or annotation.list_group_id in group_ids
        for annotation in annotations
    )

    restored = DocumentStructure.model_validate_json(
        structure.model_dump_json(exclude_none=True)
    )
    primary_flow_set = set(structure.primary_flow_block_ids)
    checks = {
        "document_id_matches": structure.document_id == document.id,
        "middle_sha256_matches": (
            structure.middle_sha256 == document.middle_sha256
        ),
        "source_pdf_sha256_matches": (
            structure.source_pdf_sha256 == document.source_pdf_sha256
        ),
        "root_section_exists": (
            structure.root_section_id in sections_by_id
        ),
        "all_content_blocks_annotated": (
            len(annotation_ids) == len(content_block_ids)
            and set(annotation_ids) == set(content_block_ids)
        ),
        "annotation_ids_unique": (
            len(annotation_ids) == len(set(annotation_ids))
        ),
        "reading_order_contiguous": (
            [item.reading_order for item in annotations]
            == list(range(len(annotations)))
        ),
        "annotations_match_source_pages": annotations_match_pages,
        "section_references_valid": valid_section_edges,
        "list_group_references_valid": list_memberships_match,
        "all_assets_registered": actual_asset_ids == expected_asset_ids,
        "discarded_blocks_preserved_in_order": (
            structure.discarded_block_ids == discarded_block_ids
        ),
        "primary_flow_is_ordered_subset": (
            [
                block_id
                for block_id in annotation_ids
                if block_id in primary_flow_set
            ]
            == structure.primary_flow_block_ids
        ),
        "roundtrip_matches": restored == structure,
    }
    return {
        "document_id": document.id,
        "source_name": document.source_name,
        "counts": {
            "pages": len(document.pages),
            "content_blocks": len(content_block_ids),
            "discarded_blocks": len(discarded_block_ids),
            "sections": len(structure.sections),
            "list_groups": len(structure.list_groups),
            "assets": len(structure.assets),
            "primary_flow_blocks": len(
                structure.primary_flow_block_ids
            ),
        },
        "checks": checks,
        "valid": all(checks.values()),
    }
