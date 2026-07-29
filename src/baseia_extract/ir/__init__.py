"""IR canônico e semântica-neutro produzido a partir do ``middle.json`` do MinerU."""

from .builder import build_document_ir, build_document_ir_batch
from .models import BlockIR, DocumentIR, LineIR, PageIR, SpanIR
from .validate import validate_document_ir

__all__ = [
    "BlockIR",
    "DocumentIR",
    "LineIR",
    "PageIR",
    "SpanIR",
    "build_document_ir",
    "build_document_ir_batch",
    "validate_document_ir",
]
