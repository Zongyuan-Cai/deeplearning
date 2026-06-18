from __future__ import annotations

from app.document.capability_registry import get_capability_registry
from app.domain.document_types import DocumentType
from app.document.providers.excel_provider import ExcelProvider
from app.document.providers.pdf_provider import PdfProvider
from app.document.providers.ppt_provider import PptProvider
from app.document.providers.text_provider import TextProvider
from app.document.providers.word_provider import WordProvider


DOCUMENT_PROVIDER_FACTORIES: dict[DocumentType, type] = {
    DocumentType.WORD: WordProvider,
    DocumentType.EXCEL: ExcelProvider,
    DocumentType.PDF: PdfProvider,
    DocumentType.PPT: PptProvider,
    DocumentType.TEXT: TextProvider,
}


DOCUMENT_CAPABILITY_MATRIX: dict[DocumentType, set[str]] = {
    DocumentType.WORD: {"read", "extract", "locate", "fill", "validate", "write", "compare", "scan_template"},
    DocumentType.EXCEL: {"read", "extract", "locate", "fill", "update_table", "validate", "write", "compare"},
    DocumentType.PDF: {"read", "extract", "summarize", "locate", "fill", "validate", "write", "scan_template"},
    DocumentType.PPT: {"read", "extract", "summarize", "locate", "fill", "validate", "write", "scan_template"},
    DocumentType.TEXT: {"read", "extract", "summarize", "locate", "fill", "compare", "validate", "write", "scan_template"},
}


_BOOTSTRAPPED = False


def _register_capability_matrix() -> None:
    registry = get_capability_registry()
    for document_type, capabilities in DOCUMENT_CAPABILITY_MATRIX.items():
        registry.register_document_profile(document_type=document_type, capabilities=set(capabilities))


def _register_providers() -> None:
    registry = get_capability_registry()
    for factory in DOCUMENT_PROVIDER_FACTORIES.values():
        provider = factory()
        registry.register_provider(provider)


def bootstrap_document_providers() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    _register_capability_matrix()
    _register_providers()

    _BOOTSTRAPPED = True


def bootstrap_document_system() -> None:
    """
    语义化入口：后续新增 pdf/ppt/text 等 provider，优先在本模块集中维护。
    """
    bootstrap_document_providers()
