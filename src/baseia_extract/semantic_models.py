"""Modelos da camada semântica derivada do IR canônico.

Esta camada referencia blocos do IR por seus IDs. Ela não copia nem
normaliza conteúdo extraído: texto, HTML, LaTeX e coordenadas permanecem
propriedade do IR de origem.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SemanticModel(BaseModel):
    """Base estrita para artefatos semânticos serializáveis."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class BlockRole(StrEnum):
    """Papel semântico atribuído a um bloco canônico do documento."""

    TITLE = "title"
    BODY = "body"
    LIST = "list"
    REFERENCE = "reference"
    ABSTRACT = "abstract"
    EQUATION = "equation"
    FIGURE = "figure"
    TABLE = "table"
    CHART = "chart"
    CODE = "code"
    ASIDE = "aside"
    OTHER = "other"


class AssetKind(StrEnum):
    FIGURE = "figure"
    TABLE = "table"
    CHART = "chart"
    EQUATION = "equation"
    CODE = "code"


class BlockAnnotation(SemanticModel):
    """Classificação de um bloco do fluxo de leitura canônico."""

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


class SectionNode(SemanticModel):
    """Nó de seção derivado de um bloco de título do IR."""

    id: str
    parent_id: str | None = None
    title_block_id: str | None = None
    level: int
    ordinal: int
    block_ids: list[str] = Field(default_factory=list)
    child_ids: list[str] = Field(default_factory=list)


class ListGroup(SemanticModel):
    """Sequência contígua de blocos de lista na mesma seção."""

    id: str
    section_id: str | None = None
    block_ids: list[str] = Field(default_factory=list)


class AssetRef(SemanticModel):
    """Referência a um bloco não textual que também integra o fluxo do IR."""

    id: str
    block_id: str
    page_id: str
    page: int
    kind: AssetKind
    section_id: str | None = None


class DocumentStructure(SemanticModel):
    """Estrutura semântica completa, não destrutiva, de um documento."""

    document_id: str
    middle_sha256: str
    source_pdf_sha256: str | None = None
    root_section_id: str
    sections: list[SectionNode] = Field(default_factory=list)
    annotations: list[BlockAnnotation] = Field(default_factory=list)
    list_groups: list[ListGroup] = Field(default_factory=list)
    assets: list[AssetRef] = Field(default_factory=list)
    primary_flow_block_ids: list[str] = Field(default_factory=list)
    discarded_block_ids: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
