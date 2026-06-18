"""重规划节点：规则修补 + 可选 LLM 重规划。"""

import json
from copy import deepcopy
from typing import Any

from app.agent.prompts import REPLAN_SYSTEM_PROMPT
from app.agent.state import AgentState
from app.core.llm_client import LLMClient, LLMClientError
from app.core.logger import get_logger

logger = get_logger("app.agent.nodes.replan")


def _rule_based_replan(steps: list[dict], step_results: dict[str, dict]) -> list[dict] | None:
    """规则修补：根据最后一个失败步骤的类型调整计划。"""
    # 找到最后一个失败步骤
    failed_step_id = None
    for step_id, result in reversed(list(step_results.items())):
        if not result.get("success", False):
            failed_step_id = step_id
            break

    if not failed_step_id:
        return None

    # 找到失败步骤在 plan 中的位置
    failed_idx = -1
    for i, s in enumerate(steps):
        if s.get("id") == failed_step_id:
            failed_idx = i
            break
    if failed_idx < 0:
        return None

    failed_step = steps[failed_idx]
    action = (failed_step.get("action_type") or "").strip().lower()

    if action == "extract":
        return _patch_extract(steps, failed_idx)
    if action == "locate":
        return _patch_locate(steps, failed_idx)
    if action == "fill":
        return _patch_fill(steps, failed_idx)

    return None


def _patch_extract(steps: list[dict], failed_idx: int) -> list[dict]:
    patched = deepcopy(steps)
    failed = patched[failed_idx]

    has_read_before = any((s.get("action_type") or "").strip().lower() == "read" for s in patched[:failed_idx])
    if not has_read_before:
        read_id = f"{failed['id']}_pre_read"
        read_step = {
            "id": read_id, "action_type": "read",
            "input_file_ids": list(failed.get("input_file_ids", [])),
            "target_file_id": failed.get("target_file_id"),
            "params": {}, "depends_on": list(failed.get("depends_on", [])),
            "allow_retry": True,
        }
        patched.insert(failed_idx, read_step)
        # 更新 extract 的依赖
        patched[failed_idx + 1]["depends_on"] = [read_id]

    patched[failed_idx + 1 if not has_read_before else failed_idx]["params"] = {
        **patched[failed_idx + 1 if not has_read_before else failed_idx].get("params", {}),
        "mode": "coarse",
    }
    return patched


def _patch_locate(steps: list[dict], failed_idx: int) -> list[dict]:
    patched = deepcopy(steps)
    params = patched[failed_idx].get("params", {})
    params["fallback_mode"] = "full_text_search"
    params["full_text_search"] = True
    params["case_sensitive"] = False
    patched[failed_idx]["params"] = params
    return patched


def _patch_fill(steps: list[dict], failed_idx: int) -> list[dict]:
    patched = deepcopy(steps)
    failed = patched[failed_idx]
    params = failed.get("params", {})
    field_values = params.get("field_values")

    if not isinstance(field_values, dict) or len(field_values) <= 1:
        params["incremental"] = True
        failed["params"] = params
        return patched

    # 拆分为单字段填充
    new_steps = []
    prev_deps = list(failed.get("depends_on", []))
    for idx, (key, value) in enumerate(field_values.items(), start=1):
        item_id = f"{failed['id']}_item_{idx}"
        new_steps.append({
            "id": item_id, "action_type": failed["action_type"],
            "input_file_ids": list(failed.get("input_file_ids", [])),
            "target_file_id": failed.get("target_file_id"),
            "params": {**params, "field_values": {key: value}},
            "depends_on": list(prev_deps), "allow_retry": True,
        })
        prev_deps = [item_id]

    return patched[:failed_idx] + new_steps + patched[failed_idx + 1:]


def replan_node(state: AgentState) -> dict:
    steps = list(state.get("plan_steps", []))
    step_results = state.get("step_results", {})
    replan_count = state.get("replan_count", 0)

    # 规则修补优先
    ruled = _rule_based_replan(steps, step_results)
    if ruled is not None:
        logger.info("replan_node: rule-based replan, %d→%d steps", len(steps), len(ruled))
        return {
            "plan_steps": ruled,
            "current_step_index": 0,
            "replan_count": replan_count + 1,
        }

    # 备用 LLM 重规划
    llm = LLMClient()
    if not llm.enabled:
        logger.warning("replan_node: LLM not available, returning original plan")
        return {"plan_steps": steps, "current_step_index": 0, "replan_count": replan_count + 1}

    try:
        trace_items = [
            {"step_id": sid, "success": r.get("success", False),
             "message": r.get("message", ""), "error_code": r.get("error_code", "")}
            for sid, r in step_results.items()
        ]
        payload = {
            "steps": steps,
            "execution_trace": trace_items,
        }
        result = llm.chat_json(
            system_prompt=REPLAN_SYSTEM_PROMPT,
            user_prompt=json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            temperature=0.1,
            metadata={"phase": "replan_node"},
        )
        new_steps = result.get("steps", []) if isinstance(result, dict) else []
        if new_steps:
            logger.info("replan_node: LLM replan generated %d steps", len(new_steps))
            return {
                "plan_steps": new_steps,
                "current_step_index": 0,
                "replan_count": replan_count + 1,
            }
    except (LLMClientError, Exception) as e:
        logger.warning("replan_node: LLM replan failed: %s", e)

    return {"plan_steps": steps, "current_step_index": 0, "replan_count": replan_count + 1}
