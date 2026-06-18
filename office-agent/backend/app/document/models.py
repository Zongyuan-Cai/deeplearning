from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal


BlockType = Literal["paragraph", "table", "cell", "header", "footer", "other"]


@dataclass
class DocumentMeta:
    file_name: str
    file_path: str
    file_type: str
    page_count: int | None = None
    sheet_names: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedTable:
    rows: List[List[str]]


@dataclass
class DocumentContentBlock:
    type: BlockType
    index: int
    text: str = ""
    table_rows: List[List[str]] = field(default_factory=list)
    location: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredField:
    name: str
    value: Any = None
    confidence: float | None = None
    source: str = ""
    required: bool = False


@dataclass
class DocumentReadResult:
    meta: DocumentMeta
    blocks: List[DocumentContentBlock] = field(default_factory=list)
    full_text: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentFillResult:
    meta: DocumentMeta
    output_path: str | None = None
    filled_fields: Dict[str, Any] = field(default_factory=dict)
    unfilled_fields: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentCompareResult:
    left_meta: DocumentMeta
    right_meta: DocumentMeta
    identical: bool = False
    differences: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentValidationResult:
    valid: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": self.issues,
            "warnings": self.warnings,
            "details": self.details,
        }


# ===== 向后兼容旧模型 =====
@dataclass
class ParsedDocument:
    file_name: str
    file_path: str
    file_type: str
    paragraphs: List[str]
    tables: List[ParsedTable]
    blocks: List[DocumentContentBlock]
    full_text: str


@dataclass
class VerificationResult:
    verify_passed: bool
    unreplaced_placeholders: List[str]
    empty_fields: List[str]
    warnings: List[str] = field(default_factory=list)
    needs_repair: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verify_passed": self.verify_passed,
            "unreplaced_placeholders": self.unreplaced_placeholders,
            "empty_fields": self.empty_fields,
            "warnings": self.warnings,
            "needs_repair": self.needs_repair,
        }


# 兼容旧命名
DocumentBlock = DocumentContentBlock