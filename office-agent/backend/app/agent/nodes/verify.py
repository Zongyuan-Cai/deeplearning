"""验证节点：确定性检查 + 可选 LLM 总结。"""

import json
from pathlib import Path
from typing import Any

from app.agent.prompts import VERIFICATION_SYSTEM_PROMPT
from app.agent.state import AgentState
from app.core.config import settings
from app.core.llm_client import LLMClient, LLMClientError
from app.core.logger import get_logger

logger = get_logger("app.agent.nodes.verify")


def _deterministic_summary(step_results: dict[str, dict], intermediate_refs: dict) -> dict:
    observations = list(step_results.values())
    failed_steps = [o for o in observations if not o.get("success", False)]

    # 收集失败信息
    failed_error_codes: list[str] = []
    for item in failed_steps:
        code = item.get("error_code")
        if isinstance(code, str) and code and code not in failed_error_codes:
            failed_error_codes.append(code)

    # 检查缺失字段
    missing_fields: list[str] = []
    extracted = intermediate_refs.get("extracted_fields", {})
    if isinstance(extracted, dict):

        def walk(prefix: str, value: Any) -> None:
            if isinstance(value, dict):
                for k, child in value.items():
                    walk(f"{prefix}.{k}" if prefix else str(k), child)
            elif isinstance(value, list):
                for i, child in enumerate(value):
                    walk(f"{prefix}[{i}]", child)
            elif value is None or (isinstance(value, str) and not value.strip()):
                missing_fields.append(prefix)

        for step_id, payload in extracted.items():
            walk(str(step_id), payload)

    # 检查输出文件
    output_files: list[str] = []
    out_paths = intermediate_refs.get("output_file_paths", [])
    if isinstance(out_paths, list):
        for p in out_paths:
            if isinstance(p, str) and p:
                output_files.append(p)
    invalid_output_files = []
    for p in output_files:
        path = Path(p)
        if not path.exists():
            invalid_output_files.append({"path": p, "reason": "missing"})
        elif path.is_file() and path.stat().st_size <= 0:
            invalid_output_files.append({"path": p, "reason": "empty"})

    # 检查汇总输出是否为空
    empty_summaries = []
    for obs in observations:
        data = obs.get("data", {})
        if not isinstance(data, dict):
            continue
        summary = data.get("summary")
        if isinstance(summary, str) and not summary.strip():
            empty_summaries.append(obs.get("step_id", "unknown"))

    checks = {
        "execution_success": {
            "passed": len(failed_steps) == 0,
            "failed_steps": [o.get("step_id") for o in failed_steps],
            "failed_error_codes": failed_error_codes,
        },
        "fields_completeness": {
            "passed": len(missing_fields) == 0,
            "missing_fields": missing_fields,
        },
        "output_generated": {
            "passed": not invalid_output_files,
            "files": output_files,
            "invalid_files": invalid_output_files,
        },
        "summary_non_empty": {
            "passed": len(empty_summaries) == 0,
            "empty_summary_steps": empty_summaries,
        },
    }

    issues: list[str] = []
    for failed in failed_steps:
        code = failed.get("error_code", "")
        msg = failed.get("message", f"Step failed: {failed.get('step_id', 'unknown')}")
        issues.append(f"[{code}] {msg}" if code else msg)
    if missing_fields:
        issues.append("Missing fields detected in extracted data.")
    if invalid_output_files:
        issues.append("Generated output file is missing or empty.")
    if empty_summaries:
        issues.append("Summary output is empty.")

    success = all(c.get("passed", False) for c in checks.values())

    return {
        "success": success,
        "summary": "Task execution completed and passed validation."
        if success
        else "Task execution completed but failed validation.",
        "issues": issues,
        "checks": checks,
    }


def verify_node(state: AgentState) -> dict:
    step_results = state.get("step_results", {})
    intermediate_refs = state.get("intermediate_refs", {})

    deterministic = _deterministic_summary(step_results, intermediate_refs)

    if settings.ENABLE_VERIFIER_LOGS:
        logger.info(
            "verify_node: success=%s issues=%s",
            deterministic.get("success"),
            len(deterministic.get("issues", [])),
        )

    llm = LLMClient()
    if not llm.enabled:
        return {"verification": deterministic}

    payload = {
        "observations": list(step_results.values()),
        "context": intermediate_refs,
        "deterministic": deterministic,
    }
    try:
        llm_result = llm.chat_json(
            system_prompt=VERIFICATION_SYSTEM_PROMPT,
            user_prompt=json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            temperature=0.0,
            metadata={"phase": "verify_node"},
        )
        if isinstance(llm_result, dict):
            merged = dict(deterministic)
            merged["llm_summary"] = llm_result
            return {"verification": merged}
    except LLMClientError:
        pass

    return {"verification": deterministic}
