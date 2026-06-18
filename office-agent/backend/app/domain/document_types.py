from __future__ import annotations

import os
import zipfile
from enum import Enum


def _normalize_key(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("-", "_")
    text = text.replace(" ", "_")
    return text


class DocumentType(str, Enum):
    WORD = "word"
    EXCEL = "excel"
    PPT = "ppt"
    PDF = "pdf"
    TEXT = "text"
    UNKNOWN = "unknown"

    @classmethod
    def aliases(cls) -> dict[str, "DocumentType"]:
        alias_map: dict[str, DocumentType] = {}

        for item in cls:
            alias_map[_normalize_key(item.name)] = item
            alias_map[_normalize_key(item.value)] = item

        alias_map.update(
            {
                "doc": cls.WORD,
                "docx": cls.WORD,
                ".doc": cls.WORD,
                ".docx": cls.WORD,
                "word_document": cls.WORD,
                "xls": cls.EXCEL,
                "xlsx": cls.EXCEL,
                "xlsm": cls.EXCEL,
                ".xls": cls.EXCEL,
                ".xlsx": cls.EXCEL,
                ".xlsm": cls.EXCEL,
                ".csv": cls.EXCEL,
                ".tsv": cls.EXCEL,
                "spreadsheet": cls.EXCEL,
                "csv": cls.EXCEL,
                "tsv": cls.EXCEL,
                "ppt": cls.PPT,
                "pptx": cls.PPT,
                ".ppt": cls.PPT,
                ".pptx": cls.PPT,
                "presentation": cls.PPT,
                "markdown": cls.TEXT,
                "md": cls.TEXT,
                ".md": cls.TEXT,
                "plain_text": cls.TEXT,
                "txt": cls.TEXT,
                ".txt": cls.TEXT,
                "portable_document": cls.PDF,
                ".pdf": cls.PDF,
            }
        )
        return alias_map

    @classmethod
    def from_any(cls, value: str | "DocumentType" | None) -> "DocumentType":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls.UNKNOWN
        key = _normalize_key(str(value))
        return cls.aliases().get(key, cls.UNKNOWN)

    @classmethod
    def normalize(cls, value: str | "DocumentType" | None) -> str:
        return cls.from_any(value).value


EXTENSION_TO_DOCUMENT_TYPE: dict[str, DocumentType] = {
    ".doc": DocumentType.WORD,
    ".docx": DocumentType.WORD,
    ".xls": DocumentType.EXCEL,
    ".xlsx": DocumentType.EXCEL,
    ".xlsm": DocumentType.EXCEL,
    ".csv": DocumentType.EXCEL,
    ".tsv": DocumentType.EXCEL,
    ".ppt": DocumentType.PPT,
    ".pptx": DocumentType.PPT,
    ".pdf": DocumentType.PDF,
    ".txt": DocumentType.TEXT,
    ".md": DocumentType.TEXT,
    ".log": DocumentType.TEXT,
    ".rtf": DocumentType.TEXT,
}


def _detect_type_from_signature(file_path: str | None) -> DocumentType:
    if not file_path:
        return DocumentType.UNKNOWN
    if not os.path.isfile(file_path):
        return DocumentType.UNKNOWN
    try:
        with open(file_path, "rb") as f:
            head = f.read(16)
    except Exception:
        return DocumentType.UNKNOWN

    if head.startswith(b"%PDF-"):
        return DocumentType.PDF

    # Office Open XML containers and many spreadsheet formats are zip-based.
    if head.startswith(b"PK\x03\x04"):
        lower = file_path.lower()
        if ".docx" in lower:
            return DocumentType.WORD
        if ".xlsx" in lower or ".xlsm" in lower:
            return DocumentType.EXCEL
        if ".pptx" in lower:
            return DocumentType.PPT

        # No/incorrect extension: inspect OOXML package folders.
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                names = set(zf.namelist())
            if any(name.startswith("word/") for name in names):
                return DocumentType.WORD
            if any(name.startswith("xl/") for name in names):
                return DocumentType.EXCEL
            if any(name.startswith("ppt/") for name in names):
                return DocumentType.PPT
        except Exception:
            return DocumentType.UNKNOWN
    return DocumentType.UNKNOWN


def detect_document_type(filename: str | None = None, ext: str | None = None, file_path: str | None = None) -> DocumentType:
    """
    根据文件名或扩展名推断文档类型。
    """
    candidate = (ext or "").strip().lower()
    if not candidate and filename:
        dot = filename.rfind(".")
        if dot != -1:
            candidate = filename[dot:].lower()

    if candidate:
        by_alias = DocumentType.from_any(candidate)
        if by_alias != DocumentType.UNKNOWN:
            return by_alias

    by_extension = EXTENSION_TO_DOCUMENT_TYPE.get(candidate, DocumentType.UNKNOWN)
    if by_extension != DocumentType.UNKNOWN:
        return by_extension

    by_signature = _detect_type_from_signature(file_path or filename)
    if by_signature != DocumentType.UNKNOWN:
        return by_signature

    return DocumentType.UNKNOWN
