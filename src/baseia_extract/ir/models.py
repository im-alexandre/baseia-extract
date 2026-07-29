"""Modelos lossless do núcleo de IR.

O IR representa a saída física do MinerU; ele deliberadamente não infere
seções, títulos ou qualquer outra semântica editorial.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IRModel(BaseModel):
    """Base estrita para manter evoluções de schema em ``attributes``."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SpanIR(IRModel):
    id: str
    type: str | None = None
    text: str | None = None
    content: str | None = None
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
    text: str | None = None
    content: str | None = None
    bbox: list[float] | None = None
    score: float | None = None
    level: int | None = None
    cross_page: bool | None = None
    image_path: str | None = None
    latex: str | None = None
    html: str | None = None
    lines: list[LineIR] = Field(default_factory=list)
    blocks: list[BlockIR] = Field(default_factory=list)
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
    """Um documento canônico derivado de um ``middle.json``.

    ``middle_sha256`` identifica precisamente o artefato MinerU. Identificadores
    externos do PDF permanecem separados para que uma reextração do mesmo PDF
    não seja confundida com uma mudança da fonte.
    """

    id: str
    source_path: str
    source_name: str
    middle_sha256: str
    source_document_id: str | None = None
    source_pdf_sha256: str | None = None
    backend: str | None = None
    backend_version: str | None = None
    pages: list[PageIR] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
