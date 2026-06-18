from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, File, Form, UploadFile

from app.api.file_uploads import persist_uploaded_files
from app.api.presenter import build_agent_response
from app.api.schemas import AgentRunRequest, AgentRunResponse
from app.api.translator import normalize_file_items
from app.api.translator import parse_capabilities_json
from app.application.agent_service import AgentApplicationService
from app.application.agent_service import AgentRunOptions
from app.core.config import settings


router = APIRouter()
agent_service = AgentApplicationService()


@router.post("/agent/run", response_model=AgentRunResponse)
async def run_agent(
    prompt: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    capabilities: str = Form(default="{}"),
    output_mode: str = Form(default="full"),
    task_type: str = Form(default="auto"),
    infer_task_type: bool = Form(default=True),
    include_execution_logs: bool = Form(default=True),
) -> AgentRunResponse:
    task_id = str(uuid.uuid4())
    upload_dir = os.path.join(settings.UPLOAD_DIR, task_id)
    file_infos = await persist_uploaded_files(files, upload_dir=upload_dir)
    options = AgentRunOptions(
        user_request=prompt,
        files=file_infos,
        base_capabilities=parse_capabilities_json(capabilities),
        output_mode=output_mode,
        task_type=task_type,
        infer_task_type=bool(infer_task_type),
        include_execution_logs=bool(include_execution_logs),
    )
    normalized = agent_service.execute_safe(options)
    return build_agent_response(normalized)


@router.post("/agent/run_json", response_model=AgentRunResponse)
def run_agent_json(payload: AgentRunRequest) -> AgentRunResponse:
    options = AgentRunOptions(
        user_request=payload.user_request,
        files=normalize_file_items(list(payload.files)),
        base_capabilities=payload.capabilities,
        output_mode=payload.output_mode,
        task_type=payload.task_type,
        infer_task_type=bool(payload.infer_task_type),
        include_execution_logs=bool(payload.include_execution_logs),
    )
    normalized = agent_service.execute_safe(options)
    return build_agent_response(normalized)
