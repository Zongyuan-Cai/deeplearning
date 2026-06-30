"""API Schemas — 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ===== 旧的兼容模型 =====

class AgentFileItem(BaseModel):
    file_id: str | None = None
    filename: str
    path: str
    role: str | None = None
    document_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunRequest(BaseModel):
    # 统一请求字段
    prompt: str = ""
    task_mode: str = "auto"
    files: list[AgentFileItem | dict[str, Any]] = Field(default_factory=list)

    # 兼容旧字段
    user_request: str = ""

    # 扩展控制
    capabilities: dict[str, Any] = Field(default_factory=dict)
    output_mode: str = "full"  # full / summary / minimal
    task_type: str = "auto"
    infer_task_type: bool = True
    include_execution_logs: bool = True

    @model_validator(mode="after")
    def _sync_prompt_and_user_request(self):
        if not self.prompt and self.user_request:
            self.prompt = self.user_request
        if not self.user_request and self.prompt:
            self.user_request = self.prompt

        if self.task_type == "auto" and self.task_mode and self.task_mode != "auto":
            self.task_type = self.task_mode
        return self


class AgentRunResponse(BaseModel):
    success: bool

    # 稳定响应字段
    result_text: str = ""
    result_files: list[dict[str, Any]] = Field(default_factory=list)
    structured_data: dict[str, Any] = Field(default_factory=dict)
    execution_trace: list[dict[str, Any]] = Field(default_factory=list)

    # 新增字段
    session_id: str = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)
    debug_log: list[dict[str, Any]] = Field(default_factory=list)

    # 兼容旧字段
    answer: str = ""
    result: dict[str, Any] = Field(default_factory=dict)


# ===== 新的 Session 模型 =====

class ChatMessage(BaseModel):
    """标准 OpenAI messages 格式。"""
    role: str  # system / user / assistant / tool
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class SessionCreateRequest(BaseModel):
    """创建会话请求。"""
    system_prompt: str | None = None


class SessionCreateResponse(BaseModel):
    """创建会话响应。"""
    session_id: str
    created_at: str


class SessionInfo(BaseModel):
    """会话信息。"""
    session_id: str
    created_at: str
    last_active: str
    message_count: int
    file_count: int


class MessageRequest(BaseModel):
    """发送消息请求。"""
    message: str
    files: list[dict[str, Any]] | None = None


class MessageResponse(BaseModel):
    """发送消息响应。"""
    success: bool
    message: str
    session_id: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    debug_log: list[dict[str, Any]] = Field(default_factory=list)


class FileUploadResponse(BaseModel):
    """文件上传响应。"""
    success: bool
    file_id: str
    filename: str
    path: str
    size: int
