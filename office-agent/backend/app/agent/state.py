"""AgentState — 全局 Agent 状态，LangGraph 各节点通过此 TypedDict 通信。"""

from typing import TypedDict


class StepResult(TypedDict, total=False):
    step_id: str
    action_type: str
    success: bool
    message: str
    data: dict
    failure_reason: str          # "retryable" | "replannable" | "non_recoverable"
    error_code: str
    produced_files: list[str]
    attempt: int


class PlanStep(TypedDict, total=False):
    id: str
    action_type: str
    input_file_ids: list[str]
    target_file_id: str | None
    params: dict
    depends_on: list[str]
    allow_retry: bool


class AgentState(TypedDict, total=False):
    # === 输入 ===
    user_request: str
    files: list[dict]
    capabilities: dict

    # === 计划 ===
    plan_steps: list[dict]
    current_step_index: int

    # === 执行 ===
    step_results: dict[str, dict]
    retry_counts: dict[str, int]
    intermediate_refs: dict
    trace: list[dict]

    # === 生命周期 ===
    replan_count: int
    max_replans: int
    max_step_retries: int
    termination_reason: str

    # === 验证 ===
    verification: dict

    # === 输出 ===
    success: bool
    final_output: dict
