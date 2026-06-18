from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class ParagraphBlock(BaseModel):
    index: int
    text: str
    style: Optional[str] = None


class TableCell(BaseModel):
    row: int
    col: int
    text: str


class TableBlock(BaseModel):
    table_index: int
    rows: List[List[str]]


class WordBlock(BaseModel):
    block_type: Literal["paragraph", "table", "table_cell", "run"]
    block_id: str
    text: str = ""
    paragraph_index: Optional[int] = None
    table_index: Optional[int] = None
    row_index: Optional[int] = None
    col_index: Optional[int] = None
    run_index: Optional[int] = None
    style: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)


class TableCellTarget(BaseModel):
    table_index: int
    row_index: int
    col_index: int
    expected_label: Optional[str] = None
    position_key: Optional[str] = None


class PlaceholderMatch(BaseModel):
    key: str
    token: str
    location_type: Literal["paragraph", "table_cell"]
    paragraph_index: Optional[int] = None
    table_index: Optional[int] = None
    row_index: Optional[int] = None
    col_index: Optional[int] = None
    text: Optional[str] = None
    match_mode: Literal["exact", "fuzzy", "pattern"] = "pattern"
    score: Optional[float] = None


class FillTarget(BaseModel):
    field: str
    value: Optional[str] = None
    target_type: Literal["placeholder", "paragraph", "table_cell"] = "placeholder"
    placeholder_token: Optional[str] = None
    paragraph_index: Optional[int] = None
    table_cell: Optional[TableCellTarget] = None
    overwrite_strategy: Literal["replace", "keep_existing"] = "replace"


class ValidationIssue(BaseModel):
    issue_type: Literal[
        "unfilled_placeholder",
        "empty_filled_value",
        "wrong_region",
        "structure_change",
        "missing_expected_field",
    ]
    severity: Literal["low", "medium", "high"] = "medium"
    message: str
    location_type: Optional[str] = None
    paragraph_index: Optional[int] = None
    table_index: Optional[int] = None
    row_index: Optional[int] = None
    col_index: Optional[int] = None
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    passed: bool
    issues: List[ValidationIssue] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    remaining_placeholders: List[dict[str, Any]] = Field(default_factory=list)
    empty_filled_fields: List[str] = Field(default_factory=list)
    wrong_region_fills: List[dict[str, Any]] = Field(default_factory=list)
    missing_expected_fields: List[str] = Field(default_factory=list)


class WriteOutputMeta(BaseModel):
    source_file: str
    output_file: str
    output_dir: str
    output_filename: str
    operation: Literal["replace_text", "append_text", "save_as"]
    avoided_overwrite: bool = True
    replaced_count: int = 0
    appended: bool = False


class TableDiff(BaseModel):
    table_index: int
    changed_cells: List[dict[str, Any]] = Field(default_factory=list)
    row_count_left: int = 0
    row_count_right: int = 0


class StructureSummaryDiff(BaseModel):
    left_summary: dict[str, Any] = Field(default_factory=dict)
    right_summary: dict[str, Any] = Field(default_factory=dict)
    differences: dict[str, Any] = Field(default_factory=dict)


class WordComparisonReport(BaseModel):
    left_file: str
    right_file: str
    text_diff: dict[str, Any] = Field(default_factory=dict)
    field_diff: dict[str, Any] = Field(default_factory=dict)
    table_diff: List[TableDiff] = Field(default_factory=list)
    structure_summary_diff: StructureSummaryDiff = Field(default_factory=StructureSummaryDiff)
    summary: dict[str, Any] = Field(default_factory=dict)


class DocumentStructure(BaseModel):
    paragraphs: List[ParagraphBlock]
    tables: List[TableBlock]