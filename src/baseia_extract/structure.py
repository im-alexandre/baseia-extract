"""Enriquecimento estrutural determinístico para o IR canônico."""

from __future__ import annotations

from collections.abc import Iterable
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
    "title": BlockRole.TITLE,
    "text": BlockRole.BODY,
    "list": BlockRole.LIST,
    "ref_text": BlockRole.REFERENCE,
    "abstract": BlockRole.ABSTRACT,
    "interline_equation": BlockRole.EQUATION,
    "image": BlockRole.FIGURE,
    "table": BlockRole.TABLE,
    "chart": BlockRole.CHART,
    "code": BlockRole.CODE,
    "aside_text": BlockRole.ASIDE,
    "page_footnote": BlockRole.ASIDE,
}

EXCLUDED_PRIMARY_TYPES = frozenset({"header", "footer", "page_number"})

ASSET_KIND_BY_ROLE: dict[BlockRole, AssetKind] = {
    BlockRole.FIGURE: AssetKind.FIGURE,
    BlockRole.TABLE: AssetKind.TABLE,
    BlockRole.CHART: AssetKind.CHART,
    BlockRole.EQUATION: AssetKind.EQUATION,
    BlockRole.CODE: AssetKind.CODE,
}


def _section_id(document_id: str, title_block_id: str) -> str:
    return f"{document_id}:section:{title_block_id}"


def _list_group_id(document_id: str, first_block_id: str) -> str:
    return f"{document_id}:list:{first_block_id}"


def _asset_id(document_id: str, block_id: str) -> str:
    return f"{document_id}:asset:{block_id}"


def _iter_content_blocks(document: DocumentIR) -> Iterable[tuple[PageIR, BlockIR]]:
    for page in document.pages:
        for block in page.blocks:
            yield page, block


def _iter_discarded_blocks(document: DocumentIR) -> Iterable[tuple[PageIR, BlockIR]]:
    for page in document.pages:
        for block in page.discarded_blocks:
            yield page, block


def _classify_role(block: BlockIR) -> BlockRole:
    if block.type is None:
        return BlockRole.OTHER
    return ROLE_BY_BLOCK_TYPE.get(block.type, BlockRole.OTHER)


def _title_level(block: BlockIR) -> int:
    return block.level if block.level is not None and block.level >= 1 else 1


def _block_has_content(block: BlockIR) -> bool:
    """Indica conteúdo sem concatenar, limpar ou alterar texto algum."""
    return bool(block.lines or block.html or block.latex or block.image_path)


def enrich_document(document: DocumentIR) -> DocumentStructure:
    """Deriva seções, listas e assets sem modificar nem duplicar o IR.

    A ordem das anotações é exatamente a ordem de ``document.pages`` e
    ``page.blocks``. IDs novos são funções dos IDs canônicos já existentes.
    """
    root_section_id = f"{document.id}:section-root"
    root = SectionNode(id=root_section_id, level=0, ordinal=0)
    sections = [root]
    section_stack = [root]
    annotations: list[BlockAnnotation] = []
    list_groups: list[ListGroup] = []
    assets: list[AssetRef] = []
    primary_flow_block_ids: list[str] = []
    active_list_group: ListGroup | None = None

    for reading_order, (page, block) in enumerate(_iter_content_blocks(document)):
        role = _classify_role(block)
        excluded = block.type in EXCLUDED_PRIMARY_TYPES

        if role is BlockRole.TITLE:
            level = _title_level(block)
            while len(section_stack) > 1 and section_stack[-1].level >= level:
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
        else:
            section = section_stack[-1]
            section.block_ids.append(block.id)

        if role is BlockRole.LIST:
            if active_list_group is None or active_list_group.section_id != section.id:
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
        discarded_block_ids=[block.id for _, block in _iter_discarded_blocks(document)],
        attributes={
            "backend": document.backend,
            "backend_version": document.backend_version,
        },
    )


def validate_structure(document: DocumentIR, structure: DocumentStructure) -> dict[str, Any]:
    """Valida cobertura, referências e serialização sem reprocessar conteúdo."""
    content_pairs = list(_iter_content_blocks(document))
    content_block_ids = [block.id for _, block in content_pairs]
    discarded_block_ids = [block.id for _, block in _iter_discarded_blocks(document)]
    annotations = structure.annotations
    annotation_ids = [item.block_id for item in annotations]
    sections_by_id = {section.id: section for section in structure.sections}
    group_ids = {group.id for group in structure.list_groups}
    expected_asset_ids = {
        annotation.block_id
        for annotation in annotations
        if annotation.role in ASSET_KIND_BY_ROLE
    }
    actual_asset_ids = {asset.block_id for asset in structure.assets}

    expected_page_by_block = {block.id: page for page, block in content_pairs}
    annotations_match_pages = all(
        (page := expected_page_by_block.get(annotation.block_id)) is not None
        and annotation.page_id == page.id
        and annotation.page == page.page
        for annotation in annotations
    )
    valid_section_edges = all(
        section.parent_id is None or section.parent_id in sections_by_id
        for section in structure.sections
    ) and all(
        child_id in sections_by_id
        for section in structure.sections
        for child_id in section.child_ids
    )
    list_memberships_match = all(
        annotation.list_group_id is None or annotation.list_group_id in group_ids
        for annotation in annotations
    )

    restored = DocumentStructure.model_validate_json(
        structure.model_dump_json(exclude_none=True)
    )
    checks = {
        "document_id_matches": structure.document_id == document.id,
        "middle_sha256_matches": structure.middle_sha256 == document.middle_sha256,
        "source_pdf_sha256_matches": structure.source_pdf_sha256
        == document.source_pdf_sha256,
        "root_section_exists": structure.root_section_id in sections_by_id,
        "all_content_blocks_annotated_in_order": annotation_ids == content_block_ids,
        "annotation_ids_unique": len(annotation_ids) == len(set(annotation_ids)),
        "reading_order_contiguous": [item.reading_order for item in annotations]
        == list(range(len(annotations))),
        "annotations_match_source_pages": annotations_match_pages,
        "section_references_valid": valid_section_edges,
        "list_group_references_valid": list_memberships_match,
        "all_assets_registered": actual_asset_ids == expected_asset_ids,
        "discarded_blocks_preserved_in_order": structure.discarded_block_ids
        == discarded_block_ids,
        "primary_flow_is_ordered_subset": [
            block_id for block_id in content_block_ids if block_id in set(structure.primary_flow_block_ids)
        ]
        == structure.primary_flow_block_ids,
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
            "primary_flow_blocks": len(structure.primary_flow_block_ids),
        },
        "checks": checks,
        "valid": all(checks.values()),
    }
