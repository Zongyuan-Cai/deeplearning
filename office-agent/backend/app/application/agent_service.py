from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from app.agent.graph import agent_graph
from app.core.config import settings
from app.domain.output_schema import normalize_agent_output_dict
from app.domain.task_config import infer_task_type
from app.document.bootstrap import bootstrap_document_providers


@dataclass
class AgentRunOptions:
    user_request: str
    files: list[dict[str, Any]]
    base_capabilities: dict[str, Any] = field(default_factory=dict)
    output_mode: str = "full"
    task_type: str = "auto"
    infer_task_type: bool = True
    include_execution_logs: bool = True


def normalize_output_mode(value: str | None) -> str:
    mode = (value or "full").strip().lower()
    if mode not in {"full", "summary", "minimal"}:
        return "full"
    return mode


def resolve_task_type(user_request: str, task_type: str | None, infer_enabled: bool) -> str:
    candidate = (task_type or "auto").strip().lower()
    if candidate and candidate != "auto":
        return candidate
    if infer_enabled:
        return infer_task_type(user_request)
    return "auto"


def build_capabilities(
    base_capabilities: dict[str, Any],
    *,
    files: list[dict[str, Any]],
    output_mode: str,
    task_type: str,
    infer_task_type_enabled: bool,
    include_execution_logs: bool,
) -> dict[str, Any]:
    merged = dict(base_capabilities or {})
    # Default to fallback planning so core flows remain runnable even when LLM is unavailable.
    merged.setdefault("allow_fallback", True)
    # Default to a lean planning profile: keep core actions first, expand only when needed.
    merged.setdefault("action_profile", "lean")
    merged.setdefault("allow_advanced_actions", False)
    input_mode = "single_file" if len(files) == 1 else ("multi_file" if len(files) > 1 else "no_file")
    merged["api_options"] = {
        "output_mode": output_mode,
        "task_type": task_type,
        "infer_task_type": infer_task_type_enabled,
        "include_execution_logs": include_execution_logs,
        "file_count": len(files),
        "input_mode": input_mode,
    }
    merged["task_type"] = task_type
    merged["input_mode"] = input_mode
    merged["requested_output_mode"] = output_mode
    return merged


def apply_output_preferences(
    normalized_result: dict[str, Any],
    *,
    output_mode: str,
    include_execution_logs: bool,
) -> dict[str, Any]:
    result = deepcopy(normalized_result)
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}

    if not include_execution_logs:
        final_output = payload.get("final_output") if isinstance(payload.get("final_output"), dict) else {}
        final_output["logs"] = {}
        payload["final_output"] = final_output
        payload["trace"] = []
        payload["observations"] = []

    if output_mode == "summary":
        payload["trace"] = []
        payload["observations"] = []
        payload["memory"] = {}
        payload["context"] = {}
    elif output_mode == "minimal":
        payload = {
            "success": payload.get("success", False),
            "session": payload.get("session", {}),
            "summary": payload.get("summary", {}),
            "execution": payload.get("execution", {}),
            "final_output": payload.get("final_output", {}),
            "task": payload.get("task", None),
        }

    payload["api"] = {
        "output_mode": output_mode,
        "include_execution_logs": include_execution_logs,
    }
    result["payload"] = payload
    return result


def build_file_resolver(files: list[dict[str, Any]]):
    file_map = {f["file_id"]: f for f in files}

    def resolve(file_id: str) -> dict[str, Any]:
        if file_id not in file_map:
            raise ValueError(f"Unknown file_id: {file_id}")
        return file_map[file_id]

    return resolve


class AgentApplicationService:
    def execute(self, options: AgentRunOptions) -> dict[str, Any]:
        bootstrap_document_providers()
        resolved_output_mode = normalize_output_mode(options.output_mode)
        include_logs = bool(options.include_execution_logs)
        resolved_task_type = resolve_task_type(
            user_request=options.user_request,
            task_type=options.task_type,
            infer_enabled=bool(options.infer_task_type),
        )
        merged_capabilities = build_capabilities(
            base_capabilities=options.base_capabilities,
            files=options.files,
            output_mode=resolved_output_mode,
            task_type=resolved_task_type,
            infer_task_type_enabled=bool(options.infer_task_type),
            include_execution_logs=include_logs,
        )

        initial_state = {
            "user_request": options.user_request,
            "files": options.files,
            "capabilities": merged_capabilities,
            "max_replans": max(0, int(settings.AGENT_MAX_REPLANS)),
            "max_step_retries": max(0, int(settings.AGENT_MAX_STEP_RETRIES)),
            "plan_steps": [],
            "current_step_index": 0,
            "step_results": {},
            "retry_counts": {},
            "intermediate_refs": {},
            "trace": [],
            "replan_count": 0,
            "termination_reason": "",
            "verification": {},
            "success": False,
            "final_output": {},
        }
        final_state = agent_graph.invoke(initial_state)
        result = final_state.get("final_output", {})
        normalized = normalize_agent_output_dict(result)
        return apply_output_preferences(
            normalized,
            output_mode=resolved_output_mode,
            include_execution_logs=include_logs,
        )

    def execute_safe(self, options: AgentRunOptions) -> dict[str, Any]:
        resolved_output_mode = normalize_output_mode(options.output_mode)
        include_logs = bool(options.include_execution_logs)
        try:
            return self.execute(options)
        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "summary": {"success": False, "summary": "Runtime execution failed", "issues": [str(e)]},
            }
            normalized = normalize_agent_output_dict(error_result)
            return apply_output_preferences(
                normalized,
                output_mode=resolved_output_mode,
                include_execution_logs=include_logs,
            )
