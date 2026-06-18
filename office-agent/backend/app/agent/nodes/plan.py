"""规划节点：LLM 生成 ActionPlan，不可用时 Fallback 规则。"""

import json
import uuid
from typing import Any

from pydantic import ValidationError

from app.agent.prompts import PLANNER_SYSTEM_PROMPT
from app.agent.state import AgentState
from app.core.config import settings
from app.core.llm_client import LLMClient, LLMClientError
from app.core.logger import get_logger
from app.document.capability_registry import get_capability_registry
from app.domain.task_config import infer_task_type

logger = get_logger("app.agent.nodes.plan")

CORE_ACTIONS = ("read", "extract", "fill", "write")


def build_planning_contract(
    user_request: str,
    files: list[dict],
    capabilities: dict[str, Any],
) -> dict[str, Any]:
    task_type = str(capabilities.get("task_type") or infer_task_type(user_request) or "auto").strip().lower()
    input_mode = capabilities.get("input_mode", "")
    allow_advanced = bool(capabilities.get("allow_advanced_actions", False))

    if task_type == "summarize":
        allowed = {"read", "summarize"}
    elif task_type == "extract":
        allowed = {"read", "extract"}
    elif task_type == "locate":
        allowed = {"read", "locate"}
    elif task_type == "validate":
        allowed = {"read", "validate"}
    elif task_type == "update_table":
        allowed = {"read", "extract", "update_table", "write"}
    elif task_type in {"fill", "scan_template"}:
        allowed = {"read", "extract", "fill", "write", "scan_template", "locate", "validate"}
    elif task_type == "compare":
        allowed = {"read", "compare", "summarize"}
    elif input_mode == "multi_file" or len(files) > 1:
        allowed = {"read", "extract", "fill", "write", "compare"}
    else:
        allowed = set(CORE_ACTIONS)

    if allow_advanced:
        allowed.update({"scan_template", "locate", "validate", "update_table", "summarize", "compare"})
        if task_type in {"fill", "scan_template"}:
            allowed.add("build_field_mapping")

    return {
        "action_profile": "lean",
        "task_type": task_type,
        "input_mode": input_mode or ("single_file" if len(files) == 1 else ("multi_file" if len(files) > 1 else "no_file")),
        "core_actions": list(CORE_ACTIONS),
        "allowed_actions": sorted(allowed),
    }


def fallback_plan(user_request: str, files: list[dict], capabilities: dict[str, Any]) -> list[dict]:
    contract = build_planning_contract(user_request, files, capabilities)
    allowed = set(contract.get("allowed_actions", []))
    mapping_allowed = "build_field_mapping" in allowed

    if not files:
        return []

    excel_files = [f for f in files if str(f.get("filename", "")).lower().endswith((".xlsx", ".xls", ".xlsm", ".csv", ".tsv"))]
    word_files = [f for f in files if str(f.get("filename", "")).lower().endswith((".docx", ".doc"))]

    steps: list[dict] = []

    if excel_files and word_files:
        source = excel_files[0]
        target = word_files[0]
        sid, tid = str(uuid.uuid4())[:8], str(uuid.uuid4())[:8]
        mid = str(uuid.uuid4())[:8]

        steps = [
            {"id": "step_scan_template", "action_type": "scan_template", "input_file_ids": [],
             "target_file_id": target["file_id"], "params": {"output_artifact_name": f"schema_{sid}"},
             "depends_on": [], "allow_retry": True},
            {"id": "step_extract_source", "action_type": "extract",
             "input_file_ids": [source["file_id"]], "target_file_id": None,
             "params": {"output_artifact_name": f"data_{tid}"}, "depends_on": [], "allow_retry": True},
        ]
        if mapping_allowed:
            steps += [
                {"id": "step_build_mapping", "action_type": "build_field_mapping", "input_file_ids": [],
                 "target_file_id": None,
                 "params": {"source_step_id": "step_extract_source",
                            "target_schema_from_artifact": f"schema_{sid}",
                            "artifact_name": f"mapping_{mid}",
                            "user_request": user_request},
                 "depends_on": ["step_scan_template", "step_extract_source"], "allow_retry": True},
                {"id": "step_fill_template", "action_type": "fill", "input_file_ids": [],
                 "target_file_id": target["file_id"],
                 "params": {"field_values_from_artifact": f"mapping_{mid}"},
                 "depends_on": ["step_build_mapping"], "allow_retry": True},
            ]
        else:
            steps.append(
                {"id": "step_fill_template", "action_type": "fill", "input_file_ids": [],
                 "target_file_id": target["file_id"], "params": {},
                 "depends_on": ["step_scan_template", "step_extract_source"], "allow_retry": True},
            )
    else:
        first = files[0]
        inferred = infer_task_type(user_request)
        if inferred == "summarize":
            steps = [
                {"id": "step_read", "action_type": "read", "input_file_ids": [first["file_id"]],
                 "target_file_id": None, "params": {}, "depends_on": [], "allow_retry": True},
                {"id": "step_summarize", "action_type": "summarize", "input_file_ids": [first["file_id"]],
                 "target_file_id": None, "params": {"source": "step_read"},
                 "depends_on": ["step_read"], "allow_retry": True},
            ]
        else:
            steps = [
                {"id": "step_extract", "action_type": "extract", "input_file_ids": [first["file_id"]],
                 "target_file_id": None, "params": {"output_artifact_name": "extract_result"},
                 "depends_on": [], "allow_retry": True},
            ]
    return steps


def llm_plan(user_request: str, files: list[dict], capabilities: dict[str, Any]) -> list[dict]:
    llm = LLMClient()
    if not llm.enabled:
        raise LLMClientError("LLM not configured")

    contract = build_planning_contract(user_request, files, capabilities)
    allowed_actions = set(contract.get("allowed_actions", []))
    registry = get_capability_registry()

    merged_capabilities = {
        "provider_capabilities": registry.export_for_prompt(allowed_actions=allowed_actions),
        "extra_capabilities": capabilities,
    }

    user_prompt = json.dumps(
        {
            "user_request": user_request,
            "available_files": files,
            "capabilities": merged_capabilities,
            "planning_contract": contract,
            "planning_hints": {
                "excel_to_word": ["scan_template", "extract", "fill", "write"],
                "summarize_single_file": ["read", "summarize"],
                "compare_multi_file": ["read", "compare", "summarize"],
            },
        },
        ensure_ascii=False, indent=2, default=str,
    )

    result = llm.chat_json(
        system_prompt=PLANNER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,
        metadata={"phase": "plan_node"},
    )
    steps = result.get("steps", []) if isinstance(result, dict) else []
    return steps


def plan_node(state: AgentState) -> dict:
    user_request = state.get("user_request", "")
    files = state.get("files", [])
    capabilities = state.get("capabilities", {})
    allow_fallback = bool(capabilities.get("allow_fallback", True))

    try:
        steps = llm_plan(user_request, files, capabilities)
        source = "llm"
    except Exception:
        if not allow_fallback:
            raise
        logger.warning("plan_node: LLM planning failed, using fallback")
        steps = fallback_plan(user_request, files, capabilities)
        source = "fallback"

    logger.info("plan_node: %s plan generated, %d steps", source, len(steps))
    return {
        "plan_steps": steps,
        "current_step_index": 0,
        "step_results": {},
        "retry_counts": {},
        "intermediate_refs": {"read_documents": {}, "extracted_fields": {}, "generated_mappings": {}, "filled_documents": {}, "output_file_paths": []},
        "trace": [],
        "replan_count": 0,
        "termination_reason": "",
    }
