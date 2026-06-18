from __future__ import annotations

from typing import Any

from app.api.schemas import AgentRunResponse


def extract_answer(result: dict[str, Any]) -> str:
    final_output = result.get("payload", {}).get("final_output", {}) if isinstance(result, dict) else {}
    if isinstance(final_output, dict):
        text = final_output.get("text", "")
        if isinstance(text, str) and text.strip():
            return text

    summary = result.get("summary", {}) if isinstance(result, dict) else {}
    if isinstance(summary, dict):
        text = summary.get("summary", "")
        if isinstance(text, str):
            return text
    return ""


def extract_response_fields(result: dict[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    payload = result.get("payload", {}) if isinstance(result, dict) else {}
    final_output = payload.get("final_output", {}) if isinstance(payload, dict) else {}

    text = ""
    if isinstance(final_output, dict):
        text = str(final_output.get("text") or "")
    if not text:
        text = extract_answer(result)

    files = final_output.get("files", []) if isinstance(final_output, dict) else []
    if not isinstance(files, list):
        files = []

    structured = final_output.get("structured", {}) if isinstance(final_output, dict) else {}
    if not isinstance(structured, dict):
        structured = {}

    trace = payload.get("trace", []) if isinstance(payload, dict) else []
    if not isinstance(trace, list):
        trace = []

    return text, files, structured, trace


def build_agent_response(normalized: dict[str, Any]) -> AgentRunResponse:
    payload = normalized.get("payload", {}) if isinstance(normalized, dict) else {}
    result_text, result_files, structured_data, execution_trace = extract_response_fields(normalized)
    return AgentRunResponse(
        success=bool(payload.get("success", False)),
        result_text=result_text,
        result_files=result_files,
        structured_data=structured_data,
        execution_trace=execution_trace,
        answer=extract_answer(normalized),
        result=normalized,
    )

