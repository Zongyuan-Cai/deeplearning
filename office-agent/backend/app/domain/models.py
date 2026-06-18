from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


@dataclass
class ParsedTable:
    rows: List[List[str]] = field(default_factory=list)


@dataclass
class ParsedDocument:
    file_name: str
    file_path: str
    paragraphs: List[str] = field(default_factory=list)
    tables: List[ParsedTable] = field(default_factory=list)
    full_text: str = ""


@dataclass
class InputFile:
    role: str  # source / template / reference
    file_name: str
    file_path: str
    paragraphs: List[str] = field(default_factory=list)
    tables: List[ParsedTable] = field(default_factory=list)
    full_text: str = ""


@dataclass
class TaskContext:
    user_prompt: str
    logs: List[str] = field(default_factory=list)

    files: List[InputFile] = field(default_factory=list)

    # 兼容旧逻辑
    file_name: str = ""
    file_path: str = ""
    full_text: str = ""
    paragraphs: List[str] = field(default_factory=list)
    tables: List[ParsedTable] = field(default_factory=list)

    template_file_name: Optional[str] = None
    template_file_path: Optional[str] = None


@dataclass
class TaskResult:
    success: bool
    message: str
    answer: str = ""
    logs: List[str] = field(default_factory=list)
    error: Optional[str] = None
    structured_data: Optional[Dict[str, Any]] = None
    output_file_path: Optional[str] = None


# ===== 新版全局业务模型（跨模块统一语言） =====


class TaskRequestModel(BaseModel):
    task_id: str | None = None
    user_request: str
    files: list["DocumentReference"] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)


class DocumentReference(BaseModel):
    file_id: str | None = None
    filename: str
    path: str
    role: str | None = None
    document_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FieldMappingItem(BaseModel):
    field: str
    value: Any = None
    source: str | None = None
    confidence: float | None = None
    normalized_field: str | None = None


class FieldMappingModel(BaseModel):
    items: list[FieldMappingItem] = Field(default_factory=list)
    by_field: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float | None = None


class OutputFileModel(BaseModel):
    path: str
    filename: str | None = None
    document_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FinalOutputModel(BaseModel):
    text: str = ""
    files: list[OutputFileModel] = Field(default_factory=list)
    structured: dict[str, Any] = Field(default_factory=dict)
    logs: dict[str, Any] = Field(default_factory=dict)


class ExecutionSummaryModel(BaseModel):
    success: bool = False
    stage_flow: list[str] = Field(default_factory=list)
    replan_count: int = 0
    attempts: int = 1
    termination_reason: str = ""
    iteration_history: list[dict[str, Any]] = Field(default_factory=list)
    retry_count: int = 0
    retry_events: list[dict[str, Any]] = Field(default_factory=list)
    failure_count: int = 0
    failure_events: list[dict[str, Any]] = Field(default_factory=list)
    total_steps: int = 0
    succeeded_steps: int = 0
    failed_steps: int = 0
    issues: list[str] = Field(default_factory=list)
    checks: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class AgentResultModel(BaseModel):
    success: bool = False
    session: dict[str, Any] = Field(default_factory=dict)
    task: TaskRequestModel | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    execution: ExecutionSummaryModel = Field(default_factory=ExecutionSummaryModel)
    final_output: FinalOutputModel = Field(default_factory=FinalOutputModel)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    memory: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
