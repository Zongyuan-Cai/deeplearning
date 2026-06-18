from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


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

    # 兼容旧字段
    answer: str = ""
    result: dict[str, Any] = Field(default_factory=dict)