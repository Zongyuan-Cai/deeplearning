"""API Routes — 路由定义。

支持新的 Session 端点和旧的兼容端点。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.agent.loop import run_agent_sync
from app.agent.tools import default_registry
from app.api.file_uploads import persist_uploaded_files
from app.api.schemas import (
    AgentRunRequest,
    AgentRunResponse,
    ChatMessage,
    FileUploadResponse,
    MessageRequest,
    MessageResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionInfo,
)
from app.api.translator import normalize_file_items, parse_capabilities_json
from app.core.config import settings
from app.core.llm_client import LLMClient
from app.core.logger import get_logger

logger = get_logger("app.api.routes")

router = APIRouter()


# ===== 工具函数 =====

def _sanitize_filename(filename: str) -> str:
    """清理文件名，防止路径遍历攻击。"""
    # 只保留文件名部分，去掉路径
    filename = os.path.basename(filename or "uploaded_file")
    # 移除危险字符
    filename = re.sub(r'[^\w\-_\.]', '_', filename)
    # 确保文件名不为空
    return filename or "uploaded_file"


# ===== Session 存储（内存） =====

class SessionData:
    def __init__(self, session_id: str, system_prompt: str | None = None):
        self.session_id = session_id
        self.messages: list[dict[str, Any]] = []
        self.files: list[dict[str, Any]] = []
        self.created_at = datetime.utcnow().isoformat() + "Z"
        self.last_active = self.created_at
        self.debug_log: list[dict[str, Any]] = []
        self.lock = asyncio.Lock()  # 并发控制锁

        # 初始化系统提示
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})
        else:
            from app.agent.prompts import SYSTEM_PROMPT
            self.messages.append({"role": "system", "content": SYSTEM_PROMPT})

    def update_active(self):
        self.last_active = datetime.utcnow().isoformat() + "Z"

    def is_expired(self, ttl_seconds: int = 3600) -> bool:
        """检查 session 是否过期。"""
        try:
            last_active = datetime.fromisoformat(self.last_active.replace("Z", "+00:00"))
            return datetime.utcnow() - last_active.replace(tzinfo=None) > timedelta(seconds=ttl_seconds)
        except Exception:
            return True


# 内存中的 session 存储
sessions: dict[str, SessionData] = {}

# Session 配置
SESSION_MAX_COUNT = 1000  # 最大 session 数量
SESSION_TTL_SECONDS = 3600  # session 过期时间（1小时）
SESSION_CLEANUP_INTERVAL = 300  # 清理间隔（5分钟）


async def cleanup_expired_sessions():
    """定期清理过期的 session。"""
    while True:
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
        expired_ids = [
            sid for sid, session in sessions.items()
            if session.is_expired(SESSION_TTL_SECONDS)
        ]
        for sid in expired_ids:
            del sessions[sid]
            logger.info("Cleaned up expired session: %s", sid)
        if expired_ids:
            logger.info("Cleaned up %d expired sessions", len(expired_ids))


# 注意：cleanup task 需要在 main.py 中启动
# 在 main.py 的 startup 事件中调用: asyncio.create_task(cleanup_expired_sessions())


# ===== 新的 Session 端点 =====

@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session(request: SessionCreateRequest | None = None):
    """创建新会话。"""
    # 检查 session 数量限制
    if len(sessions) >= SESSION_MAX_COUNT:
        # 尝试清理过期 session
        expired_ids = [
            sid for sid, session in sessions.items()
            if session.is_expired(SESSION_TTL_SECONDS)
        ]
        for sid in expired_ids:
            del sessions[sid]

        # 如果还是太多，拒绝创建
        if len(sessions) >= SESSION_MAX_COUNT:
            raise HTTPException(
                status_code=429,
                detail="Too many sessions. Please try again later."
            )

    session_id = str(uuid.uuid4())
    system_prompt = request.system_prompt if request else None
    sessions[session_id] = SessionData(session_id, system_prompt)
    logger.info("Created session: %s", session_id)
    return SessionCreateResponse(
        session_id=session_id,
        created_at=sessions[session_id].created_at,
    )


@router.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    """获取会话信息。"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[session_id]
    if session.is_expired(SESSION_TTL_SECONDS):
        del sessions[session_id]
        raise HTTPException(status_code=404, detail="Session expired")
    return SessionInfo(
        session_id=session.session_id,
        created_at=session.created_at,
        last_active=session.last_active,
        message_count=len(session.messages),
        file_count=len(session.files),
    )


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话。"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del sessions[session_id]
    return {"success": True, "message": "Session deleted"}


@router.post("/sessions/{session_id}/files", response_model=FileUploadResponse)
async def upload_file_to_session(
    session_id: str,
    file: UploadFile = File(...),
):
    """上传文件到会话。"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    if session.is_expired(SESSION_TTL_SECONDS):
        del sessions[session_id]
        raise HTTPException(status_code=404, detail="Session expired")

    # 清理文件名，防止路径遍历
    safe_filename = _sanitize_filename(file.filename)
    file_id = str(uuid.uuid4())
    upload_dir = os.path.join(settings.UPLOAD_DIR, session_id)
    os.makedirs(upload_dir, exist_ok=True)

    # 检查文件大小限制（100MB）
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 100MB.")

    file_path = os.path.join(upload_dir, f"{file_id}_{safe_filename}")
    with open(file_path, "wb") as f:
        f.write(content)

    file_info = {
        "file_id": file_id,
        "filename": safe_filename,
        "path": file_path,
        "size": len(content),
    }
    session.files.append(file_info)
    session.update_active()

    return FileUploadResponse(
        success=True,
        file_id=file_id,
        filename=safe_filename,
        path=file_path,
        size=len(content),
    )


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    request: MessageRequest,
):
    """发送消息到会话（同步响应）。"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    if session.is_expired(SESSION_TTL_SECONDS):
        del sessions[session_id]
        raise HTTPException(status_code=404, detail="Session expired")

    # 执行 agent（使用锁防止并发，将所有修改操作放在锁内部）
    async with session.lock:
        try:
            # 如果请求中有新文件，添加到会话
            if request.files:
                for f in request.files:
                    if f not in session.files:
                        session.files.append(f)

            # 添加用户消息
            session.messages.append({"role": "user", "content": request.message})

            llm = LLMClient()
            debug_log = []
            # 使用 asyncio.to_thread 包装同步调用，避免阻塞事件循环
            await asyncio.to_thread(
                run_agent_sync,
                messages=session.messages,
                files=session.files,
                registry=default_registry,
                llm=llm,
                debug_log=debug_log,
            )
            session.debug_log.extend(debug_log)
            session.update_active()

            # 提取最后的 assistant 消息
            assistant_message = ""
            for msg in reversed(session.messages):
                if msg.get("role") == "assistant":
                    assistant_message = msg.get("content", "")
                    break

            return MessageResponse(
                success=True,
                message=assistant_message,
                session_id=session_id,
                messages=session.messages,
                debug_log=debug_log,
            )
        except Exception as e:
            logger.exception("Agent execution failed")
            error_msg = f"处理失败：{str(e)}"
            session.messages.append({"role": "assistant", "content": error_msg})
            return MessageResponse(
                success=False,
                message=error_msg,
                session_id=session_id,
                messages=session.messages,
            )


@router.post("/sessions/{session_id}/messages/stream")
async def send_message_stream(
    session_id: str,
    request: MessageRequest,
):
    """发送消息到会话（SSE 流式响应）。"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    if session.is_expired(SESSION_TTL_SECONDS):
        del sessions[session_id]
        raise HTTPException(status_code=404, detail="Session expired")

    # 检查是否有正在进行的请求
    if session.lock.locked():
        raise HTTPException(
            status_code=409,
            detail="A request is already in progress for this session. Please wait."
        )

    # 保存请求数据，以便在锁内使用
    request_files = request.files
    request_message = request.message

    async def event_generator():
        queue = asyncio.Queue()

        async def on_text(text: str):
            await queue.put({"type": "text", "data": {"text": text}})

        async def on_tool_call(info: dict):
            await queue.put({"type": "tool_call", "data": info})

        async def on_tool_result(info: dict):
            await queue.put({"type": "tool_result", "data": info})

        async def on_debug(info: dict):
            await queue.put({"type": "debug", "data": info})

        # 在后台运行 agent
        async def run():
            async with session.lock:
                try:
                    # 将消息和文件修改移到锁内部
                    if request_files:
                        for f in request_files:
                            if f not in session.files:
                                session.files.append(f)

                    session.messages.append({"role": "user", "content": request_message})

                    from app.agent.loop import run_agent
                    llm = LLMClient()
                    debug_log = []
                    await run_agent(
                        messages=session.messages,
                        files=session.files,
                        registry=default_registry,
                        llm=llm,
                        debug_log=debug_log,
                        on_text=on_text,
                        on_tool_call=on_tool_call,
                        on_tool_result=on_tool_result,
                        on_debug=on_debug,
                    )
                    session.debug_log.extend(debug_log)
                    session.update_active()
                    await queue.put({"type": "done", "data": {"success": True}})
                except Exception as e:
                    logger.exception("Agent execution failed in stream")
                    await queue.put({"type": "error", "data": {"message": str(e)}})
                finally:
                    await queue.put(None)  # 结束信号

        # 启动后台任务
        asyncio.create_task(run())

        # 从队列中读取事件
        while True:
            event = await queue.get()
            if event is None:
                break
            event_type = event.get("type", "message")
            data = json.dumps(event.get("data", {}), ensure_ascii=False)
            yield f"event: {event_type}\ndata: {data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ===== 旧的兼容端点 =====

def _extract_result_files(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从消息中提取生成的文件。"""
    result_files = []
    for msg in messages:
        if msg.get("role") == "tool":
            try:
                content = json.loads(msg.get("content", "{}"))
                if isinstance(content, dict):
                    output_path = content.get("output_path")
                    if output_path and os.path.exists(output_path):
                        result_files.append({
                            "path": output_path,
                            "filename": os.path.basename(output_path),
                        })
            except Exception:
                pass
    return result_files


@router.post("/agent/run", response_model=AgentRunResponse)
async def run_agent_legacy(
    prompt: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    capabilities: str = Form(default="{}"),
    output_mode: str = Form(default="full"),
    task_type: str = Form(default="auto"),
    infer_task_type: bool = Form(default=True),
    include_execution_logs: bool = Form(default=True),
) -> AgentRunResponse:
    """旧的兼容端点（内部创建临时 session）。"""
    task_id = str(uuid.uuid4())
    upload_dir = os.path.join(settings.UPLOAD_DIR, task_id)
    file_infos = await persist_uploaded_files(files, upload_dir=upload_dir)

    # 创建临时 session
    session = SessionData(task_id)
    session.files = file_infos
    sessions[task_id] = session

    # 添加用户消息
    session.messages.append({"role": "user", "content": prompt})

    # 执行 agent
    try:
        llm = LLMClient()
        await asyncio.to_thread(
            run_agent_sync,
            messages=session.messages,
            files=session.files,
            registry=default_registry,
            llm=llm,
        )

        # 提取最后的 assistant 消息
        assistant_message = ""
        for msg in reversed(session.messages):
            if msg.get("role") == "assistant":
                assistant_message = msg.get("content", "")
                break

        # 提取生成的文件
        result_files = _extract_result_files(session.messages)

        return AgentRunResponse(
            success=True,
            result_text=assistant_message,
            answer=assistant_message,
            session_id=task_id,
            result_files=result_files,
        )
    except Exception as e:
        logger.exception("Agent execution failed")
        return AgentRunResponse(
            success=False,
            result_text=f"处理失败：{str(e)}",
            answer=f"处理失败：{str(e)}",
            session_id=task_id,
        )


@router.post("/agent/run_json", response_model=AgentRunResponse)
async def run_agent_json(payload: AgentRunRequest) -> AgentRunResponse:
    """旧的 JSON 兼容端点。"""
    task_id = str(uuid.uuid4())

    # 创建临时 session
    session = SessionData(task_id)
    session.files = normalize_file_items(list(payload.files))
    sessions[task_id] = session

    # 添加用户消息
    user_message = payload.prompt or payload.user_request
    session.messages.append({"role": "user", "content": user_message})

    # 执行 agent
    try:
        llm = LLMClient()
        await asyncio.to_thread(
            run_agent_sync,
            messages=session.messages,
            files=session.files,
            registry=default_registry,
            llm=llm,
        )

        # 提取最后的 assistant 消息
        assistant_message = ""
        for msg in reversed(session.messages):
            if msg.get("role") == "assistant":
                assistant_message = msg.get("content", "")
                break

        # 提取生成的文件
        result_files = _extract_result_files(session.messages)

        return AgentRunResponse(
            success=True,
            result_text=assistant_message,
            answer=assistant_message,
            session_id=task_id,
            result_files=result_files,
        )
    except Exception as e:
        logger.exception("Agent execution failed")
        return AgentRunResponse(
            success=False,
            result_text=f"处理失败：{str(e)}",
            answer=f"处理失败：{str(e)}",
            session_id=task_id,
        )
