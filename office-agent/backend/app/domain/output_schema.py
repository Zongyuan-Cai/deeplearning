from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.domain.models import (
    AgentResultModel,
    DocumentReference,
    ExecutionSummaryModel,
    FinalOutputModel,
    OutputFileModel,
    TaskRequestModel,
)


class OutputSchema(BaseModel):
    schema_name: str = "agent.output.v1"
    payload: AgentResultModel


def _to_output_file(item: dict[str, Any]) -> OutputFileModel:
    path = str(item.get("path") or "")
    filename = item.get("filename")
    if not filename and path:
        filename = path.replace("\\", "/").split("/")[-1]
    return OutputFileModel(
        path=path,
        filename=str(filename) if filename else None,
        document_type=item.get("document_type"),
        metadata={k: v for k, v in item.items() if k not in {"path", "filename", "document_type"}},
    )


def _build_execution_summary(raw: dict[str, Any]) -> ExecutionSummaryModel:
    lifecycle = raw.get("lifecycle") if isinstance(raw.get("lifecycle"), dict) else {}
    observations = raw.get("observations") if isinstance(raw.get("observations"), list) else []
    summary = raw.get("summary") if isinstance(raw.get("summary"), dict) else {}
    context = raw.get("context") if isinstance(raw.get("context"), dict) else {}
    state = context.get("state") if isinstance(context.get("state"), dict) else {}
    refs = state.get("intermediate_refs") if isinstance(state.get("intermediate_refs"), dict) else {}
    retry_events = refs.get("retry_events") if isinstance(refs.get("retry_events"), list) else []
    failure_events = refs.get("failure_events") if isinstance(refs.get("failure_events"), list) else []

    succeeded = 0
    failed = 0
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        if obs.get("success") is True:
            succeeded += 1
        elif obs.get("success") is False:
            failed += 1

    return ExecutionSummaryModel(
        success=bool(raw.get("success", False)),
        stage_flow=list(lifecycle.get("stage_flow", []) or []),
        replan_count=int(lifecycle.get("replan_count", 0) or 0),
        attempts=int(lifecycle.get("attempts", 1) or 1),
        termination_reason=str(lifecycle.get("termination_reason", "") or ""),
        iteration_history=[item for item in lifecycle.get("iteration_history", []) if isinstance(item, dict)],
        retry_count=len(retry_events),
        retry_events=[item for item in retry_events if isinstance(item, dict)],
        failure_count=len(failure_events),
        failure_events=[item for item in failure_events if isinstance(item, dict)],
        total_steps=len(observations),
        succeeded_steps=succeeded,
        failed_steps=failed,
        issues=list(summary.get("issues", []) or []),
        checks=dict(summary.get("checks", {}) or {}),
        message=str(summary.get("summary") or ""),
    )


def _build_task_model(raw: dict[str, Any]) -> TaskRequestModel | None:
    session = raw.get("session") if isinstance(raw.get("session"), dict) else {}
    context = raw.get("context") if isinstance(raw.get("context"), dict) else {}

    user_request = str(session.get("user_prompt") or "")
    if not user_request:
        return None

    file_refs: list[DocumentReference] = []
    state = context.get("state") if isinstance(context.get("state"), dict) else {}
    files = state.get("files") if isinstance(state.get("files"), list) else []
    for item in files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        filename = str(item.get("filename") or item.get("file_id") or "")
        if not filename and path:
            filename = path.replace("\\", "/").split("/")[-1]
        if not filename:
            continue
        file_refs.append(
            DocumentReference(
                file_id=item.get("file_id"),
                filename=filename,
                path=path,
                role=item.get("role"),
                document_type=item.get("document_type"),
                metadata={k: v for k, v in item.items() if k not in {"file_id", "filename", "path", "role", "document_type"}},
            )
        )

    return TaskRequestModel(
        task_id=str(session.get("task_id") or "") or None,
        user_request=user_request,
        files=file_refs,
        capabilities={},
        options={},
    )


def _build_final_output(raw: dict[str, Any]) -> FinalOutputModel:
    final_output = raw.get("final_output") if isinstance(raw.get("final_output"), dict) else {}

    text = str(final_output.get("text") or raw.get("text_result") or "")

    files_raw = final_output.get("files")
    if not isinstance(files_raw, list):
        files_raw = raw.get("file_result") if isinstance(raw.get("file_result"), list) else []

    files: list[OutputFileModel] = []
    for item in files_raw:
        if isinstance(item, dict) and item.get("path"):
            files.append(_to_output_file(item))

    structured = final_output.get("structured")
    if not isinstance(structured, dict):
        structured = raw.get("structured_result") if isinstance(raw.get("structured_result"), dict) else {}

    logs = final_output.get("logs")
    if not isinstance(logs, dict):
        logs = raw.get("logs") if isinstance(raw.get("logs"), dict) else {}

    return FinalOutputModel(
        text=text,
        files=files,
        structured=structured,
        logs=logs,
    )


def normalize_agent_output(raw_result: dict[str, Any]) -> OutputSchema:
    raw = raw_result if isinstance(raw_result, dict) else {}

    payload = AgentResultModel(
        success=bool(raw.get("success", False)),
        session=dict(raw.get("session", {}) or {}),
        task=_build_task_model(raw),
        summary=dict(raw.get("summary", {}) or {}),
        execution=_build_execution_summary(raw),
        final_output=_build_final_output(raw),
        observations=list(raw.get("observations", []) or []),
        trace=list(raw.get("trace", []) or []),
        memory=dict(raw.get("memory", {}) or {}),
        context=dict(raw.get("context", {}) or {}),
    )
    return OutputSchema(payload=payload)


def normalize_agent_output_dict(raw_result: dict[str, Any]) -> dict[str, Any]:
    schema = normalize_agent_output(raw_result)
    if hasattr(schema, "model_dump"):
        return schema.model_dump()
    return schema.dict()
