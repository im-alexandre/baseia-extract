# %% [markdown]
# # 06 — Enrich Structure
#
# Cria uma camada estrutural determinística sobre o IR canônico.
#
# Princípios:
#
# - não altera o `DocumentIR`;
# - referencia os nós do IR por IDs determinísticos;
# - não usa LLM, NLP ou heurísticas específicas de domínio;
# - não realiza chunking;
# - preserva a ordem de leitura produzida pelo MinerU;
# - organiza títulos em seções;
# - agrupa listas contíguas;
# - registra figuras, tabelas, gráficos, fórmulas e código;
# - mantém blocos não classificados acessíveis.
#
# Entrada:
#
#     artifacts/ir_prototype/**/document_ir.json
#
# Saída:
#
#     artifacts/structure_enrichment/**/structure_ir.json

# %%
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

# %% [markdown]
# ## Configuração

# %%
PROJECT_ROOT = Path.cwd()

ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

IR_DIR = ARTIFACTS_DIR / "ir_prototype"
IR_GLOB = "**/document_ir.json"

OUTPUT_DIR = ARTIFACTS_DIR / "structure_enrichment"

MAX_DOCUMENTS: int | None = None
FAIL_ON_INVALID = True

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# %% [markdown]
# ## Modelos do IR canônico
#
# Quando os modelos forem movidos para `src/baseia/ir/models.py`,
# substituir esta seção por imports.


# %%
class IRModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class SpanIR(IRModel):
    id: str
    type: str | None = None
    text: str | None = None
    bbox: list[float] | None = None
    score: float | None = None
    latex: str | None = None
    html: str | None = None
    image_path: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class LineIR(IRModel):
    id: str
    bbox: list[float] | None = None
    score: float | None = None
    spans: list[SpanIR] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class BlockIR(IRModel):
    id: str
    block_index: int | None = None
    type: str | None = None
    bbox: list[float] | None = None
    score: float | None = None
    level: int | None = None
    cross_page: bool | None = None
    image_path: str | None = None
    latex: str | None = None
    html: str | None = None
    lines: list[LineIR] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class PageIR(IRModel):
    id: str
    page: int
    width: float | None = None
    height: float | None = None
    blocks: list[BlockIR] = Field(default_factory=list)
    discarded_blocks: list[BlockIR] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class DocumentIR(IRModel):
    id: str
    source_path: str
    source_name: str
    source_sha256: str
    backend: str | None = None
    backend_version: str | None = None
    pages: list[PageIR] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


# %% [markdown]
# ## Modelos da camada estrutural
#
# Esta camada não duplica o conteúdo textual do IR.
# Ela apenas referencia IDs dos nós canônicos.

# %%
BlockRole = Literal[
    "title",
    "body",
    "list",
    "reference",
    "abstract",
    "equation",
    "figure",
    "table",
    "chart",
    "code",
    "aside",
    "other",
]


class StructureModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class BlockAnnotation(StructureModel):
    block_id: str
    page_id: str
    page: int
    reading_order: int
    role: BlockRole
    source_type: str | None = None
    section_id: str | None = None
    list_group_id: str | None = None
    excluded_from_primary_flow: bool = False
    attributes: dict[str, Any] = Field(default_factory=dict)


class SectionNode(StructureModel):
    id: str
    parent_id: str | None = None
    title_block_id: str | None = None
    level: int
    ordinal: int
    block_ids: list[str] = Field(default_factory=list)
    child_ids: list[str] = Field(default_factory=list)


class ListGroup(StructureModel):
    id: str
    section_id: str | None = None
    block_ids: list[str] = Field(default_factory=list)


class AssetRef(StructureModel):
    id: str
    block_id: str
    page_id: str
    page: int
    kind: Literal[
        "figure",
        "table",
        "chart",
        "equation",
        "code",
    ]
    section_id: str | None = None


class DocumentStructure(StructureModel):
    document_id: str
    source_sha256: str
    root_section_id: str
    sections: list[SectionNode] = Field(default_factory=list)
    annotations: list[BlockAnnotation] = Field(default_factory=list)
    list_groups: list[ListGroup] = Field(default_factory=list)
    assets: list[AssetRef] = Field(default_factory=list)
    primary_flow_block_ids: list[str] = Field(default_factory=list)
    discarded_block_ids: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


# %% [markdown]
# ## Mapeamentos determinísticos

# %%
ROLE_BY_BLOCK_TYPE: dict[str, BlockRole] = {
    "title": "title",
    "text": "body",
    "list": "list",
    "ref_text": "reference",
    "abstract": "abstract",
    "interline_equation": "equation",
    "image": "figure",
    "table": "table",
    "chart": "chart",
    "code": "code",
    "aside_text": "aside",
    "page_footnote": "aside",
}

EXCLUDED_PRIMARY_TYPES = {
    "header",
    "footer",
    "page_number",
}

ASSET_ROLE_TO_KIND = {
    "figure": "figure",
    "table": "table",
    "chart": "chart",
    "equation": "equation",
    "code": "code",
}


# %% [markdown]
# ## Helpers


# %%
def child_id(
    parent_id: str,
    kind: str,
    index: int,
) -> str:
    return f"{parent_id}:{kind}{index:04d}"


def sha256_file(path: Path) -> str:
    """Calcula o SHA-256 de um arquivo sem carregá-lo inteiro na memória."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def fallback_sha256(payload: dict[str, Any]) -> str:
    """
    Gera uma identidade estável quando o arquivo-fonte não está disponível.

    O hash é calculado sobre o conteúdo do IR antes da inclusão dos IDs.
    """
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(serialized).hexdigest()


def assign_block_ids(
    blocks: list[dict[str, Any]],
    *,
    page_id: str,
    collection_name: str,
) -> None:
    """Adiciona IDs determinísticos a blocos, linhas e spans."""
    for block_index, block in enumerate(blocks):
        block_id = f"{page_id}:{collection_name}-block{block_index:04d}"
        block.setdefault("id", block_id)

        # Preserva o índice original do MinerU quando existente.
        if block.get("block_index") is None:
            original_index = block.get("index") or block.get("attributes", {}).get(
                "index"
            )

            if original_index is not None:
                block["block_index"] = original_index

        lines = block.get("lines") or []

        for line_index, line in enumerate(lines):
            line_id = f"{block_id}:line{line_index:04d}"
            line.setdefault("id", line_id)

            spans = line.get("spans") or []

            for span_index, span in enumerate(spans):
                span.setdefault(
                    "id",
                    f"{line_id}:span{span_index:04d}",
                )

                # Alguns dados MinerU usam `content`; o IR usa `text`.
                if "text" not in span and "content" in span:
                    span["text"] = span.pop("content")


def hydrate_document_ir(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Completa campos de identidade ausentes no protótipo do IR.

    Não altera o arquivo em disco; apenas normaliza o payload carregado.
    """
    source_path_value = payload.get("source_path")
    source_path = (
        Path(source_path_value) if isinstance(source_path_value, str) else None
    )

    source_sha256 = payload.get("source_sha256")

    if not source_sha256:
        if source_path is not None and source_path.is_file():
            source_sha256 = sha256_file(source_path)
        else:
            source_sha256 = fallback_sha256(payload)

        payload["source_sha256"] = source_sha256

    payload.setdefault(
        "id",
        f"doc:{source_sha256[:16]}",
    )

    if not payload.get("source_name"):
        payload["source_name"] = (
            source_path.name if source_path is not None else payload["id"]
        )

    # Compatibilidade com o nome usado no protótipo anterior.
    if "backend_version" not in payload and "version_name" in payload:
        payload["backend_version"] = payload.pop("version_name")

    document_id = payload["id"]
    pages = payload.get("pages") or []

    for page_index, page in enumerate(pages):
        page_number = page.get("page", page_index)
        page_id = f"{document_id}:page{int(page_number):04d}"

        page.setdefault("id", page_id)

        assign_block_ids(
            page.get("blocks") or [],
            page_id=page_id,
            collection_name="content",
        )

        assign_block_ids(
            page.get("discarded_blocks") or [],
            page_id=page_id,
            collection_name="discarded",
        )

    return payload


def load_document_ir(
    path: Path,
) -> DocumentIR:
    payload = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise TypeError(f"O IR em {path} não contém um objeto JSON.")

    hydrated = hydrate_document_ir(payload)

    return DocumentIR.model_validate(hydrated)


def write_json(
    payload: Any,
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def block_text(block: BlockIR) -> str:
    return "\n".join(
        span.text.strip()
        for line in block.lines
        for span in line.spans
        if span.text and span.text.strip()
    )


def normalize_title_level(
    block: BlockIR,
) -> int:
    if block.level is not None and block.level >= 1:
        return block.level

    return 1


def classify_role(
    block: BlockIR,
) -> BlockRole:
    if block.type is None:
        return "other"

    return ROLE_BY_BLOCK_TYPE.get(
        block.type,
        "other",
    )


def is_excluded_from_primary_flow(
    block: BlockIR,
) -> bool:
    return block.type in EXCLUDED_PRIMARY_TYPES


def iter_content_blocks(
    document: DocumentIR,
) -> Iterable[tuple[PageIR, BlockIR]]:
    for page in document.pages:
        for block in page.blocks:
            yield page, block


def iter_discarded_blocks(
    document: DocumentIR,
) -> Iterable[tuple[PageIR, BlockIR]]:
    for page in document.pages:
        for block in page.discarded_blocks:
            yield page, block


# %% [markdown]
# ## Construção da árvore de seções
#
# O MinerU fornece blocos `title` e, quando disponível, `level`.
#
# Regras:
#
# - todo documento possui uma seção raiz artificial de nível `0`;
# - um título abre uma nova seção;
# - o pai é a seção aberta mais próxima com nível menor;
# - blocos seguintes pertencem à seção atualmente aberta;
# - títulos sem `level` são tratados como nível `1`.


# %%
class SectionBuilder:
    def __init__(self, document_id: str) -> None:
        self.document_id = document_id
        self.root_id = f"{document_id}:section-root"

        self.sections: list[SectionNode] = [
            SectionNode(
                id=self.root_id,
                parent_id=None,
                title_block_id=None,
                level=0,
                ordinal=0,
            )
        ]

        self.by_id: dict[str, SectionNode] = {self.root_id: self.sections[0]}

        self.stack: list[SectionNode] = [self.sections[0]]

        self.next_ordinal = 1

    @property
    def current(self) -> SectionNode:
        return self.stack[-1]

    def open_section(
        self,
        title_block: BlockIR,
    ) -> SectionNode:
        level = normalize_title_level(title_block)

        while len(self.stack) > 1 and self.stack[-1].level >= level:
            self.stack.pop()

        parent = self.stack[-1]
        section_id = child_id(
            self.document_id,
            "section",
            self.next_ordinal,
        )

        section = SectionNode(
            id=section_id,
            parent_id=parent.id,
            title_block_id=title_block.id,
            level=level,
            ordinal=self.next_ordinal,
            block_ids=[title_block.id],
        )

        parent.child_ids.append(section.id)

        self.sections.append(section)
        self.by_id[section.id] = section
        self.stack.append(section)
        self.next_ordinal += 1

        return section

    def append_block(
        self,
        block_id: str,
    ) -> None:
        self.current.block_ids.append(block_id)


# %% [markdown]
# ## Agrupamento de listas
#
# Blocos `list` contíguos dentro da mesma seção formam um grupo.
# A continuidade é quebrada por qualquer bloco não-lista ou mudança de seção.


# %%
class ListGroupBuilder:
    def __init__(self, document_id: str) -> None:
        self.document_id = document_id
        self.groups: list[ListGroup] = []
        self.current: ListGroup | None = None
        self.next_ordinal = 1

    def append(
        self,
        *,
        block_id: str,
        section_id: str | None,
    ) -> str:
        if self.current is None or self.current.section_id != section_id:
            self.current = ListGroup(
                id=child_id(
                    self.document_id,
                    "list",
                    self.next_ordinal,
                ),
                section_id=section_id,
            )

            self.groups.append(self.current)
            self.next_ordinal += 1

        self.current.block_ids.append(block_id)

        return self.current.id

    def break_group(self) -> None:
        self.current = None


# %% [markdown]
# ## Enriquecimento


# %%
def enrich_document(
    document: DocumentIR,
) -> DocumentStructure:
    section_builder = SectionBuilder(document.id)
    list_builder = ListGroupBuilder(document.id)

    annotations: list[BlockAnnotation] = []
    assets: list[AssetRef] = []
    primary_flow_block_ids: list[str] = []

    reading_order = 0
    asset_ordinal = 1

    for page, block in iter_content_blocks(document):
        role = classify_role(block)
        excluded = is_excluded_from_primary_flow(block)

        if role == "title":
            section = section_builder.open_section(block)
        else:
            section = section_builder.current
            section_builder.append_block(block.id)

        if role == "list":
            list_group_id = list_builder.append(
                block_id=block.id,
                section_id=section.id,
            )
        else:
            list_builder.break_group()
            list_group_id = None

        annotation = BlockAnnotation(
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
                "has_text": bool(block_text(block)),
                "cross_page": block.cross_page,
            },
        )

        annotations.append(annotation)

        if not excluded:
            primary_flow_block_ids.append(block.id)

        if role in ASSET_ROLE_TO_KIND:
            assets.append(
                AssetRef(
                    id=child_id(
                        document.id,
                        "asset",
                        asset_ordinal,
                    ),
                    block_id=block.id,
                    page_id=page.id,
                    page=page.page,
                    kind=ASSET_ROLE_TO_KIND[role],
                    section_id=section.id,
                )
            )

            asset_ordinal += 1

        reading_order += 1

    discarded_block_ids = [block.id for _, block in iter_discarded_blocks(document)]

    return DocumentStructure(
        document_id=document.id,
        source_sha256=document.source_sha256,
        root_section_id=section_builder.root_id,
        sections=section_builder.sections,
        annotations=annotations,
        list_groups=list_builder.groups,
        assets=assets,
        primary_flow_block_ids=primary_flow_block_ids,
        discarded_block_ids=discarded_block_ids,
        attributes={
            "backend": document.backend,
            "backend_version": document.backend_version,
        },
    )


# %% [markdown]
# ## Validação


# %%
def validate_structure(
    document: DocumentIR,
    structure: DocumentStructure,
) -> dict[str, Any]:
    content_block_ids = [block.id for _, block in iter_content_blocks(document)]

    discarded_block_ids = [block.id for _, block in iter_discarded_blocks(document)]

    annotation_block_ids = [annotation.block_id for annotation in structure.annotations]

    section_ids = {section.id for section in structure.sections}

    annotation_section_ids = {
        annotation.section_id
        for annotation in structure.annotations
        if annotation.section_id is not None
    }

    list_group_ids = {group.id for group in structure.list_groups}

    annotation_list_group_ids = {
        annotation.list_group_id
        for annotation in structure.annotations
        if annotation.list_group_id is not None
    }

    asset_block_ids = {asset.block_id for asset in structure.assets}

    expected_asset_block_ids = {
        annotation.block_id
        for annotation in structure.annotations
        if annotation.role in ASSET_ROLE_TO_KIND
    }

    serialized = structure.model_dump_json(exclude_none=True)

    restored = DocumentStructure.model_validate_json(serialized)

    checks = {
        "all_content_blocks_annotated": (annotation_block_ids == content_block_ids),
        "annotation_ids_unique": (
            len(annotation_block_ids) == len(set(annotation_block_ids))
        ),
        "reading_order_contiguous": (
            [annotation.reading_order for annotation in structure.annotations]
            == list(range(len(structure.annotations)))
        ),
        "all_annotation_sections_exist": (annotation_section_ids <= section_ids),
        "all_annotation_list_groups_exist": (
            annotation_list_group_ids <= list_group_ids
        ),
        "all_assets_registered": (asset_block_ids == expected_asset_block_ids),
        "discarded_blocks_preserved": (
            structure.discarded_block_ids == discarded_block_ids
        ),
        "primary_flow_is_subset": (
            set(structure.primary_flow_block_ids) <= set(content_block_ids)
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
            "primary_flow_blocks": len(structure.primary_flow_block_ids),
        },
        "checks": checks,
        "valid": all(checks.values()),
    }


# %% [markdown]
# ## Descoberta dos IRs

# %%
ir_paths = sorted(IR_DIR.glob(IR_GLOB))

if MAX_DOCUMENTS is not None:
    ir_paths = ir_paths[:MAX_DOCUMENTS]

print(f"document_ir.json encontrados: {len(ir_paths)}")

for path in ir_paths[:10]:
    print(path)

if len(ir_paths) > 10:
    print(f"... e mais {len(ir_paths) - 10}")


# %% [markdown]
# ## Execução em lote

# %%
structures: list[DocumentStructure] = []
validation_reports: list[dict[str, Any]] = []

for index, ir_path in enumerate(
    ir_paths,
    start=1,
):
    document = load_document_ir(ir_path)
    structure = enrich_document(document)
    validation = validate_structure(
        document,
        structure,
    )

    relative_parent = ir_path.parent.relative_to(IR_DIR)

    output_path = OUTPUT_DIR / relative_parent / "structure_ir.json"

    write_json(
        structure.model_dump(
            mode="json",
            exclude_none=True,
        ),
        output_path,
    )

    structures.append(structure)
    validation_reports.append(validation)

    status = "OK" if validation["valid"] else "ERRO"

    print(
        f"[{index:03d}/{len(ir_paths):03d}] "
        f"{status} "
        f"{document.source_name} "
        f"sections={len(structure.sections)} "
        f"lists={len(structure.list_groups)} "
        f"assets={len(structure.assets)}"
    )


# %% [markdown]
# ## Relatório consolidado

# %%
role_counts = Counter(
    annotation.role for structure in structures for annotation in structure.annotations
)

source_type_counts = Counter(
    annotation.source_type or "<none>"
    for structure in structures
    for annotation in structure.annotations
)

asset_kind_counts = Counter(
    asset.kind for structure in structures for asset in structure.assets
)

summary = {
    "documents": len(structures),
    "valid_documents": sum(report["valid"] for report in validation_reports),
    "invalid_documents": sum(not report["valid"] for report in validation_reports),
    "sections": sum(len(structure.sections) for structure in structures),
    "list_groups": sum(len(structure.list_groups) for structure in structures),
    "assets": sum(len(structure.assets) for structure in structures),
    "annotations": sum(len(structure.annotations) for structure in structures),
    "primary_flow_blocks": sum(
        len(structure.primary_flow_block_ids) for structure in structures
    ),
    "discarded_blocks": sum(
        len(structure.discarded_block_ids) for structure in structures
    ),
    "role_counts": dict(role_counts.most_common()),
    "source_type_counts": dict(source_type_counts.most_common()),
    "asset_kind_counts": dict(asset_kind_counts.most_common()),
}

write_json(
    summary,
    OUTPUT_DIR / "summary.json",
)

write_json(
    validation_reports,
    OUTPUT_DIR / "validation_report.json",
)

summary


# %% [markdown]
# ## Diagnóstico das seções

# %%
section_levels = Counter(
    section.level for structure in structures for section in structure.sections
)

empty_sections = [
    {
        "document_id": structure.document_id,
        "section_id": section.id,
        "level": section.level,
        "title_block_id": section.title_block_id,
    }
    for structure in structures
    for section in structure.sections
    if not section.block_ids
]

section_diagnostics = {
    "level_counts": {
        str(level): count for level, count in sorted(section_levels.items())
    },
    "empty_sections": empty_sections,
}

write_json(
    section_diagnostics,
    OUTPUT_DIR / "section_diagnostics.json",
)

section_diagnostics


# %% [markdown]
# ## Falhar explicitamente em inconsistência

# %%
invalid_reports = [report for report in validation_reports if not report["valid"]]

if FAIL_ON_INVALID and invalid_reports:
    raise AssertionError(
        json.dumps(
            invalid_reports,
            ensure_ascii=False,
            indent=2,
        )
    )

print("Enriquecimento estrutural concluído.")
