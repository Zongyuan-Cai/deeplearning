"""Agent Loop — ReAct 推理循环。

替代旧的 graph.py，使用 LLM 自主决策调用工具。
"""

from __future__ import annotations

import asyncio
import json
import time
from copy import deepcopy
from typing import Any

from app.agent.tools import ToolRegistry, default_registry
from app.core.llm_client import LLMClient, LLMResponse
from app.core.logger import get_logger

logger = get_logger("app.agent.loop")


async def run_agent(
    messages: list[dict[str, Any]],
    files: list[dict[str, Any]],
    registry: ToolRegistry | None = None,
    llm: LLMClient | None = None,
    max_steps: int = 20,
    debug_log: list[dict[str, Any]] | None = None,
    on_text: Any = None,
    on_tool_call: Any = None,
    on_tool_result: Any = None,
    on_debug: Any = None,
) -> list[dict[str, Any]]:
    """ReAct 主循环。

    Args:
        messages: 标准 OpenAI messages 格式（会被原地修改）
        files: 当前会话的文件列表
        registry: 工具注册表，默认使用 default_registry
        llm: LLM 客户端，默认创建新实例
        max_steps: 最大步数
        debug_log: 调试日志列表
        on_text: 文本输出回调
        on_tool_call: 工具调用回调
        on_tool_result: 工具结果回调
        on_debug: 调试信息回调

    Returns:
        修改后的 messages 列表
    """
    if registry is None:
        registry = default_registry
    if llm is None:
        llm = LLMClient()

    tools_schema = registry.get_schemas()

    for step in range(max_steps):
        logger.info("Agent step %d/%d", step + 1, max_steps)

        # 1. 调 LLM（使用 asyncio.to_thread 避免阻塞事件循环）
        try:
            response = await asyncio.to_thread(
                llm.chat_with_tools,
                messages=messages,
                tools=tools_schema,
            )
        except Exception as e:
            logger.exception("LLM call failed at step %d", step)
            # 添加错误消息并结束
            messages.append({
                "role": "assistant",
                "content": f"抱歉，处理过程中遇到错误：{str(e)}",
            })
            break

        # 2. 记录 debug
        if debug_log is not None:
            debug_entry = {
                "step": step,
                "request_messages": deepcopy(messages),
                "request_tools": tools_schema,
                "response": response.raw_response,
                "duration_ms": response.duration_ms,
                "usage": response.usage,
            }
            debug_log.append(debug_entry)
            if on_debug:
                await on_debug(debug_entry)

        # 3. 追加 assistant message
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content}
        if response.tool_calls:
            assistant_msg["tool_calls"] = response.tool_calls
        messages.append(assistant_msg)

        # 通知文本输出
        if response.content and on_text:
            await on_text(response.content)

        # 4. 无 tool_calls → Agent 认为任务完成
        if not response.tool_calls:
            logger.info("Agent completed at step %d (no tool calls)", step)
            break

        # 5. 执行每个 tool_call，追加 tool message
        for tc in response.tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            logger.info("Executing tool: %s", name)
            if on_tool_call:
                await on_tool_call({"name": name, "arguments": args})

            result = registry.execute(name, args, files=files)

            if on_tool_result:
                await on_tool_result({"name": name, "result": result})

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    return messages


def run_agent_sync(
    messages: list[dict[str, Any]],
    files: list[dict[str, Any]],
    registry: ToolRegistry | None = None,
    llm: LLMClient | None = None,
    max_steps: int = 20,
    debug_log: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """同步版本的 ReAct 主循环。"""
    if registry is None:
        registry = default_registry
    if llm is None:
        llm = LLMClient()

    tools_schema = registry.get_schemas()

    for step in range(max_steps):
        logger.info("Agent step %d/%d", step + 1, max_steps)

        # 1. 调 LLM
        try:
            response = llm.chat_with_tools(messages=messages, tools=tools_schema)
        except Exception as e:
            logger.exception("LLM call failed at step %d", step)
            messages.append({
                "role": "assistant",
                "content": f"抱歉，处理过程中遇到错误：{str(e)}",
            })
            break

        # 2. 记录 debug
        if debug_log is not None:
            debug_log.append({
                "step": step,
                "request_messages": deepcopy(messages),
                "request_tools": tools_schema,
                "response": response.raw_response,
                "duration_ms": response.duration_ms,
                "usage": response.usage,
            })

        # 3. 追加 assistant message
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content}
        if response.tool_calls:
            assistant_msg["tool_calls"] = response.tool_calls
        messages.append(assistant_msg)

        # 4. 无 tool_calls → Agent 认为任务完成
        if not response.tool_calls:
            logger.info("Agent completed at step %d (no tool calls)", step)
            break

        # 5. 执行每个 tool_call，追加 tool message
        for tc in response.tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            logger.info("Executing tool: %s", name)
            result = registry.execute(name, args, files=files)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    return messages
