"""执行节点：单步执行 + 失败分类 + 重试 + FillFields 自动对齐。"""

import random
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.agent.state import AgentState
from app.agent.tools import TOOL_MAP
from app.core.config import settings
from app.core.llm_client import LLMClient, LLMClientError
from app.core.logger import get_logger

logger = get_logger("app.agent.nodes.execute")

# 失败分类标签
FAILURE_RETRYABLE = "retryable"
FAILURE_REPLANNABLE = "replannable"
FAILURE_NON_RECOVERABLE = "non_recoverable"

# 不可自动重试的写操作
MUTATING_ACTIONS = {"fill", "write", "update_table"}

# 可重试的错误码
RETRYABLE_ERROR_CODES = {"TIMEOUT", "RATE_LIMIT", "NETWORK", "SERVER"}


def _classify_failure(step: dict, message: str, error_code: str = "") -> str:
    code = (error_code or "").strip().upper()
    if code in {"TIMEOUT", "RATE_LIMIT", "NETWORK"}:
        return FAILURE_RETRYABLE
    if code in {"HANDLER_NOT_FOUND", "CAPABILITY_UNSUPPORTED", "DEPENDENCY"}:
        return FAILURE_REPLANNABLE
    if code in {"INVALID_INPUT", "FILE_NOT_FOUND"}:
        return FAILURE_NON_RECOVERABLE

    text = (message or "").lower()
    if any(kw in text for kw in ["timeout", "timed out", "tempor", "rate limit", "429", "connection", "network", "unavailable", "busy", "try again"]):
        return FAILURE_RETRYABLE
    if any(kw in text for kw in ["no handler", "unsupported", "dependency", "provider", "capability", "not support"]):
        return FAILURE_REPLANNABLE

    if step.get("allow_retry", True):
        return FAILURE_RETRYABLE
    return FAILURE_NON_RECOVERABLE


def _classify_error_code(message: str) -> str:
    text = (message or "").lower()
    if "timed out" in text or "timeout" in text:
        return "TIMEOUT"
    if "rate limit" in text or "429" in text:
        return "RATE_LIMIT"
    if any(kw in text for kw in ["connection", "network", "unavailable", "dns", "socket"]):
        return "NETWORK"
    if "not found" in text and ("file" in text or "path" in text):
        return "FILE_NOT_FOUND"
    if any(kw in text for kw in ["invalid", "missing required", "unknown file_id"]):
        return "INVALID_INPUT"
    return "UNKNOWN"


def _is_retry_allowed(step: dict) -> bool:
    if not step.get("allow_retry", True):
        return False
    action = (step.get("action_type") or "").strip().lower()
    if action in MUTATING_ACTIONS:
        return bool(step.get("params", {}).get("retry_mutating", False))
    return True


def _compute_backoff(attempt: int) -> float:
    base = max(0.0, float(settings.AGENT_RETRY_BACKOFF_BASE_SECONDS))
    cap = max(base, float(settings.AGENT_RETRY_BACKOFF_MAX_SECONDS))
    jitter = max(0.0, float(settings.AGENT_RETRY_BACKOFF_JITTER_SECONDS))
    if base <= 0:
        return 0.0
    delay = min(cap, base * (2 ** max(0, attempt - 1)))
    delay += random.uniform(0.0, jitter)
    return max(0.0, delay)


# ─── FillFields 自动对齐逻辑（从旧 fill_fields.py 提取） ───

def _normalize_key(value: str) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _collect_template_fields(refs: dict) -> list[str]:
    fields: list[str] = []
    extracted = refs.get("extracted_fields", {})
    if isinstance(extracted, dict):
        for value in extracted.values():
            if not isinstance(value, dict):
                continue
            for key in ("template_fields", "analyzed"):
                sub = value.get(key)
                if isinstance(sub, dict):
                    for f in sub.get("fields", []) or []:
                        if isinstance(f, str) and f.strip():
                            fields.append(f.strip())
    read_docs = refs.get("read_documents", {})
    if isinstance(read_docs, dict):
        for value in read_docs.values():
            if not isinstance(value, dict):
                continue
            structure = value.get("structure", {})
            if isinstance(structure, dict):
                for item in structure.get("tag_candidates", []) or []:
                    if isinstance(item, dict):
                        tag = item.get("tag", "")
                    else:
                        tag = str(item)
                    if tag.strip():
                        fields.append(tag.strip())
    dedup: list[str] = []
    seen = set()
    for f in fields:
        k = _normalize_key(f)
        if k and k not in seen:
            seen.add(k)
            dedup.append(f)
    return dedup


def _collect_source_values(refs: dict) -> dict[str, str]:
    source: dict[str, str] = {}
    extracted = refs.get("extracted_fields", {})
    if not isinstance(extracted, dict):
        return source
    for value in extracted.values():
        if not isinstance(value, dict):
            continue
        records = value.get("records")
        if isinstance(records, list) and records and isinstance(records[0], dict):
            for k, v in records[0].items():
                if k is not None and v not in (None, ""):
                    source[str(k)] = str(v)
        values = value.get("values")
        if isinstance(values, list) and len(values) >= 2:
            headers = values[0] if isinstance(values[0], list) else []
            row = values[1] if isinstance(values[1], list) else []
            for idx, h in enumerate(headers):
                if h in (None, ""):
                    continue
                cv = row[idx] if idx < len(row) else None
                if cv not in (None, ""):
                    source[str(h)] = str(cv)
    return source


def _align_template_with_source(template_fields: list[str], source_values: dict[str, str]) -> dict:
    if not template_fields or not source_values:
        return {}
    norm_source = {_normalize_key(k): v for k, v in source_values.items() if _normalize_key(k)}
    result: dict[str, str] = {}
    for field in template_fields:
        nf = _normalize_key(field)
        if not nf:
            continue
        if nf in norm_source:
            result[field] = norm_source[nf]
            continue
        for sk, sv in norm_source.items():
            if nf in sk or sk in nf:
                result[field] = sv
                break
    return result


def _infer_field_values(refs: dict) -> dict:
    generated = refs.get("generated_mappings", {})
    if isinstance(generated, dict):
        for value in reversed(list(generated.values())):
            if isinstance(value, dict) and value:
                if isinstance(value.get("field_values"), dict):
                    return dict(value.get("field_values") or {})
                return dict(value)

    extracted = refs.get("extracted_fields", {})
    if isinstance(extracted, dict):
        for value in reversed(list(extracted.values())):
            if isinstance(value, dict) and value:
                if isinstance(value.get("field_values"), dict):
                    return dict(value.get("field_values") or {})
                if isinstance(value.get("records"), list) and value["records"]:
                    first = value["records"][0]
                    if isinstance(first, dict):
                        return dict(first)

    template_fields = _collect_template_fields(refs)
    source_values = _collect_source_values(refs)
    return _align_template_with_source(template_fields, source_values)


def _resolve_params(params: dict, refs: dict) -> dict:
    resolved = deepcopy(params)

    # 优先使用显式 artifact 引用
    artifact_ref = resolved.pop("field_values_from_artifact", None)
    if artifact_ref and isinstance(refs.get("generated_mappings", {}).get(artifact_ref), dict):
        fv = refs["generated_mappings"][artifact_ref].get("field_values")
        if isinstance(fv, dict):
            resolved["field_values"] = fv

    # 有 field_values 就跳过推断
    if not resolved.get("field_values"):
        inferred = _infer_field_values(refs)
        if inferred:
            resolved["field_values"] = inferred

    return resolved


# ─── LLM-based summarize / compare ───

def _get_content_from_refs(refs: dict) -> str:
    """从 intermediate_refs 中提取已有文档内容。"""
    read_docs = refs.get("read_documents", {})
    if isinstance(read_docs, dict):
        for v in read_docs.values():
            if isinstance(v, dict):
                for key in ("text", "full_text", "content"):
                    text = v.get(key)
                    if isinstance(text, str) and text.strip():
                        return text.strip()
                structure = v.get("structure", {})
                if isinstance(structure, dict):
                    for key in ("text", "full_text"):
                        text = structure.get(key)
                        if isinstance(text, str) and text.strip():
                            return text.strip()

    extracted = refs.get("extracted_fields", {})
    if isinstance(extracted, dict):
        for v in extracted.values():
            if isinstance(v, dict):
                for key in ("text", "full_text", "content"):
                    text = v.get(key)
                    if isinstance(text, str) and text.strip():
                        return text.strip()
    return ""


def _execute_summarize(step: dict, refs: dict, files: list[dict], user_request: str) -> dict:
    """Summarize: 优先用 LLM 总结上下文中的内容，否则读文件。"""
    params = step.get("params", {})
    file_path = ""
    filename = ""

    input_file_ids = step.get("input_file_ids", [])
    if input_file_ids:
        file_info = _resolve_file(input_file_ids[0], files)
        file_path = file_info.get("path", "")
        filename = file_info.get("filename", "")
    elif step.get("target_file_id"):
        file_info = _resolve_file(step["target_file_id"], files)
        file_path = file_info.get("path", "")
        filename = file_info.get("filename", "")
    elif params.get("source"):
        # Look up the source step's file from intermediate refs
        source_data = refs.get("read_documents", {}).get(params["source"], {})
        if isinstance(source_data, dict):
            pass  # content is used below
    elif files:
        # Last resort: use the first available file
        file_info = files[0]
        file_path = file_info.get("path", "")
        filename = file_info.get("filename", "")

    # 尝试从上下文获取内容
    content = _get_content_from_refs(refs)

    llm = LLMClient()
    if llm.enabled and content:
        try:
            summary = llm.summarize_text(text=content, instruction=user_request or "Summarize the content concisely")
            return {"success": True, "message": "Summary generated via LLM", "data": {"summary": summary}}
        except LLMClientError:
            pass

    # 使用 DocumentService (不需要 LLM，返回文本预览)
    if file_path:
        from app.document.service import DocumentService
        svc = DocumentService()
        result = svc.summarize_document(file_path=file_path, filename=filename)
        return {"success": result.success, "message": result.message,
                "data": result.data if isinstance(result.data, dict) else {}, "output_path": result.output_path}

    # 无 LLM 也无文件：直接从已有内容生成简单摘要
    if content:
        import textwrap
        short = " ".join(content.split())[:500]
        return {"success": True, "message": "Basic summary from context", "data": {"summary": short}}

    return {"success": False, "message": "No content or file available for summarization", "data": {}}


def _execute_compare(step: dict, refs: dict, files: list[dict], user_request: str) -> dict:
    """Compare: 读取两个文件，用 LLM 比较差异。"""
    params = step.get("params", {})
    input_ids = step.get("input_file_ids", [])

    if len(input_ids) >= 2:
        left = _resolve_file(input_ids[0], files)
        right = _resolve_file(input_ids[1], files)
        left_path = left.get("path", "")
        right_path = right.get("path", "")
    else:
        return {"success": False, "message": "compare requires at least 2 input files", "data": {}}

    from app.document.service import DocumentService
    svc = DocumentService()
    result = svc.compare_documents(left_file_path=left_path, right_file_path=right_path)
    return {"success": result.success, "message": result.message,
            "data": result.data if isinstance(result.data, dict) else {}, "output_path": result.output_path}


# ─── LLM-based build_field_mapping ───

def _execute_build_field_mapping(step: dict, refs: dict) -> dict:
    params = step.get("params", {})
    source_step_id = params.get("source_step_id", "")
    target_schema_artifact = params.get("target_schema_from_artifact", "")
    user_request = params.get("user_request", "")
    artifact_name = params.get("artifact_name") or f"{step['id']}_mapping"

    extracted = refs.get("extracted_fields", {})
    source_data = extracted.get(source_step_id, {}) if isinstance(extracted, dict) else {}

    scanned = refs.get("generated_mappings", {}).get(target_schema_artifact) if isinstance(refs.get("generated_mappings"), dict) else None
    if isinstance(scanned, dict):
        target_fields = scanned.get("fields", [])
    else:
        # 尝试从 read_documents 获取 tag_candidates
        read_docs = refs.get("read_documents", {})
        target_fields = []
        for v in read_docs.values():
            if isinstance(v, dict):
                structure = v.get("structure", {})
                if isinstance(structure, dict):
                    for item in structure.get("tag_candidates", []) or []:
                        if isinstance(item, dict):
                            target_fields.append(item.get("tag", ""))
                        elif isinstance(item, str):
                            target_fields.append(item)

    llm = LLMClient()
    if llm.enabled and target_fields:
        try:
            result = llm.match_source_to_template(
                template_placeholders=list(target_fields),
                source_content=source_data,
                instruction=user_request or "Map source data to template fields",
            )
            field_values = result if isinstance(result, dict) else {}
        except LLMClientError:
            field_values = {}
    else:
        field_values = {f: "" for f in target_fields}

    refs.setdefault("generated_mappings", {})
    refs["generated_mappings"][artifact_name] = {"field_values": field_values, "fields": list(field_values.keys())}

    return {
        "success": True,
        "message": f"Field mapping built for {len(field_values)} fields",
        "data": {"field_values": field_values, "artifact_name": artifact_name},
    }


# ─── 主执行函数 ───

def execute_node(state: AgentState) -> dict:
    steps = state.get("plan_steps", [])
    idx = state.get("current_step_index", 0)
    step_results = dict(state.get("step_results", {}))
    retry_counts = dict(state.get("retry_counts", {}))
    refs = dict(state.get("intermediate_refs", {}))
    trace = list(state.get("trace", []))

    if idx >= len(steps):
        return {"termination_reason": "all_steps_completed"}

    step = steps[idx]
    step_id = step.get("id", f"step_{idx}")
    action_type = (step.get("action_type") or "").strip().lower()
    current_attempt = retry_counts.get(step_id, 0)

    # 检查依赖
    for dep_id in step.get("depends_on", []):
        dep_result = step_results.get(dep_id)
        if dep_result is None:
            result = {
                "step_id": step_id, "action_type": action_type, "success": False,
                "message": f"Dependency not executed: {dep_id}",
                "failure_reason": FAILURE_REPLANNABLE, "error_code": "DEPENDENCY",
                "attempt": current_attempt, "data": {}, "produced_files": [],
            }
            step_results[step_id] = result
            return {"step_results": step_results, "trace": trace}

        if not dep_result.get("success"):
            result = {
                "step_id": step_id, "action_type": action_type, "success": False,
                "message": f"Dependency failed: {dep_id}",
                "failure_reason": FAILURE_REPLANNABLE, "error_code": "DEPENDENCY",
                "attempt": current_attempt, "data": {}, "produced_files": [],
            }
            step_results[step_id] = result
            return {"step_results": step_results, "trace": trace}

    # 工具解析
    tool = TOOL_MAP.get(action_type)
    if tool is None:
        result = {
            "step_id": step_id, "action_type": action_type, "success": False,
            "message": f"No tool registered for action_type={action_type}",
            "failure_reason": FAILURE_REPLANNABLE, "error_code": "HANDLER_NOT_FOUND",
            "attempt": current_attempt, "data": {}, "produced_files": [],
        }
        step_results[step_id] = result
        return {"step_results": step_results, "trace": trace}

    # 执行工具
    start_ts = datetime.now(timezone.utc).isoformat()
    start_perf = time.perf_counter()

    try:
        # 需要上下文感知的特殊 action
        if action_type == "build_field_mapping":
            raw = _execute_build_field_mapping(step, refs)
        elif action_type == "summarize":
            raw = _execute_summarize(step, refs, state.get("files", []), state.get("user_request", ""))
        elif action_type == "compare":
            raw = _execute_compare(step, refs, state.get("files", []), state.get("user_request", ""))
        else:
            # 解析输入文件
            input_file_ids = step.get("input_file_ids", [])
            target_file_id = step.get("target_file_id")
            params = deepcopy(step.get("params", {}))

            file_path = ""
            filename = ""
            if input_file_ids:
                file_info = _resolve_file(input_file_ids[0], state.get("files", []))
                file_path = file_info.get("path", "")
                filename = file_info.get("filename", "")
            elif target_file_id:
                file_info = _resolve_file(target_file_id, state.get("files", []))
                file_path = file_info.get("path", "")
                filename = file_info.get("filename", "")

            # Fill 操作的自动对齐
            if action_type == "fill":
                params = _resolve_params(params, refs)

            raw = tool.invoke({"file_path": file_path, "filename": filename, **params})
            if hasattr(raw, "model_dump"):
                raw = raw.model_dump()
            if not isinstance(raw, dict):
                raw = {"success": False, "message": str(raw), "data": {}}

        success = bool(raw.get("success", False))
        message = str(raw.get("message", ""))
        data = raw.get("data", {}) if isinstance(raw.get("data"), dict) else {}
        error_code = raw.get("error_code", "")
        produced_files = []
        if raw.get("output_path"):
            produced_files.append(raw["output_path"])

        # 失败分类
        if success:
            failure_reason = ""
            # 更新 intermediate_refs
            if action_type == "read":
                refs.setdefault("read_documents", {})[step_id] = data
            elif action_type == "extract":
                refs.setdefault("extracted_fields", {})[step_id] = data
            elif action_type in ("fill", "write"):
                refs.setdefault("filled_documents", {})[step_id] = data
                out_paths = refs.setdefault("output_file_paths", [])
                for pf in produced_files:
                    if pf not in out_paths:
                        out_paths.append(pf)
        else:
            failure_reason = _classify_failure(step, message, error_code)
            error_code = error_code or _classify_error_code(message)

    except Exception as exc:
        success = False
        message = str(exc)
        error_code = _classify_error_code(message)
        failure_reason = _classify_failure(step, message, error_code)
        data = {}
        produced_files = []

    duration_ms = max(0, int((time.perf_counter() - start_perf) * 1000))
    end_ts = datetime.now(timezone.utc).isoformat()

    result = {
        "step_id": step_id, "action_type": action_type, "success": success,
        "message": message, "failure_reason": failure_reason, "error_code": error_code,
        "attempt": current_attempt, "data": data, "produced_files": produced_files,
    }
    step_results[step_id] = result

    trace.append({
        "step_id": step_id, "action_type": action_type, "success": success,
        "message": message, "failure_reason": failure_reason, "error_code": error_code,
        "started_at": start_ts, "finished_at": end_ts, "duration_ms": duration_ms,
        "attempt": current_attempt,
    })

    # 决定是否推进步骤
    advance = False
    if success:
        advance = True
        if step_id in retry_counts:
            del retry_counts[step_id]
    else:
        can_retry = (
            failure_reason == FAILURE_RETRYABLE
            and _is_retry_allowed(step)
            and current_attempt < state.get("max_step_retries", 1)
        )
        if can_retry:
            retry_counts[step_id] = current_attempt + 1
            backoff = _compute_backoff(current_attempt + 1)
            if backoff > 0:
                time.sleep(backoff)
        else:
            advance = True

    return {
        "step_results": step_results,
        "retry_counts": retry_counts,
        "intermediate_refs": refs,
        "trace": trace,
        "current_step_index": idx + 1 if advance else idx,
    }


def _resolve_file(file_id: str, files: list[dict]) -> dict:
    for f in files:
        if f.get("file_id") == file_id:
            return f
    return {}
