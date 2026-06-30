# 重构计划：Agent 层改造

## 目标

将固定流水线（plan→execute→verify→replan→finalize）改为 ReAct 推理循环，让 LLM 成为真正的决策者。

---

## Phase 1：核心改造（LLM + Tools + Agent Loop）

### 1.1 LLMClient 增加 tool calling 支持

**文件**: `backend/app/core/llm_client.py`

- 新增 `chat_with_tools()` 方法：
  - 接收 `messages: list[dict]`（标准 OpenAI messages 格式）+ `tools: list[dict]`（function schema）
  - 构造 payload 时将 tools 作为 `tools` 字段传入（OpenAI function calling 协议）
  - 返回结构化结果：`LLMResponse(content, tool_calls, usage, finish_reason, duration_ms)`
  - 保留现有的 retry/backoff 逻辑
- 新增 `LLMResponse` dataclass：
  ```python
  @dataclass
  class LLMResponse:
      content: str | None           # LLM 的文本回复
      tool_calls: list[dict]        # tool_calls 列表 [{id, type, function: {name, arguments}}]
      usage: dict                   # {prompt_tokens, completion_tokens, total_tokens}
      finish_reason: str            # "stop" / "tool_calls" / "length"
      duration_ms: int              # 请求耗时
      raw_response: dict            # 完整的原始 response JSON（给调试面板用）
  ```
- 不改动现有的 `chat()`、`chat_json()`、`chat_structured()` 方法，保持向后兼容

### 1.2 Tool Registry

**新建文件**: `backend/app/agent/tools.py`（替换 `tools/__init__.py` + `tools/all_tools.py` + `tools/base.py`）

- `ToolRegistry` 类：
  - `register(name, description, parameters_schema, handler)` — 注册工具
  - `get_schemas() -> list[dict]` — 返回所有工具的 OpenAI function schema（供 LLM 调用）
  - `execute(name, arguments) -> dict` — 按名称查找并执行工具
- 每个工具是一个普通函数，签名统一为 `(files, **kwargs) -> dict`，其中 files 是当前会话的文件列表
- 工具 handler 内部通过 `DocumentService` 调用文档处理能力

核心工具列表：

| 工具名 | 功能 | 底层调用 |
|--------|------|----------|
| `read_file` | 读取文档内容和结构 | `DocumentService.read_document` |
| `extract_data` | 从文档提取结构化数据 | `DocumentService.extract_fields` |
| `fill_template` | 模板字段填充 | `DocumentService.fill_document` |
| `write_file` | 写入文件到输出目录 | `DocumentService.write_document` |
| `compare_files` | 对比两份文档 | `DocumentService.compare_documents` |
| `execute_code` | 在沙箱中执行 Python 代码 | subprocess |
| `list_files` | 列出当前会话文件信息 | 直接读取 files 列表 |

### 1.3 execute_code 工具

**新建文件**: `backend/app/agent/sandbox.py`

- 用 `subprocess` 执行 Python 代码，传入方式为将代码写入临时 .py 文件
- 执行环境限制：超时（默认 30s）、无网络、stdout/stderr 上限（防止输出过大）
- 注入预加载的常用库（pandas、openpyxl 等），并将当前会话的文件路径作为变量注入
- 返回 `{"stdout": str, "stderr": str, "result": Any, "error": str | None, "duration_ms": int}`

### 1.4 Agent Loop

**重写文件**: `backend/app/agent/loop.py`（替换 `graph.py`）

核心逻辑：

```python
async def run_agent(messages, files, registry, llm, max_steps=20, debug_log=None):
    """ReAct 主循环。messages 会被原地修改。"""
    tools_schema = registry.get_schemas()

    for step in range(max_steps):
        # 1. 调 LLM
        response = llm.chat_with_tools(messages=messages, tools=tools_schema)

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
        assistant_msg = {"role": "assistant", "content": response.content}
        if response.tool_calls:
            assistant_msg["tool_calls"] = response.tool_calls
        messages.append(assistant_msg)

        # 4. 无 tool_calls → Agent 认为任务完成
        if not response.tool_calls:
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

            result = registry.execute(name, args, files=files)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    return messages
```

### 1.5 Agent State 简化

**重写文件**: `backend/app/agent/state.py`

```python
from typing import TypedDict

class AgentState(TypedDict, total=False):
    messages: list[dict]      # 标准 OpenAI messages 格式
    files: list[dict]         # 当前会话的文件列表
    metadata: dict            # session_id, max_steps, debug 等控制参数
```

删除 `StepResult`、`PlanStep` 以及所有旧的字段。

### 1.6 System Prompt

**重写文件**: `backend/app/agent/prompts.py`

新的 system prompt 需要告诉 LLM：
- 它是一个 Office Agent，处理办公文档相关需求
- 它有哪些工具可用（由 tools schema 自动传入，prompt 中只需说明角色和行为规范）
- 它应该自主决定调用工具的顺序和参数
- 对于数据分析类需求，应该使用 execute_code 工具
- 每次回复用户时，给出清晰的文字说明 + 必要时附带文件

---

## Phase 2：API 改造（Session + SSE + Debug）

### 2.1 Session 管理

**修改文件**: `backend/app/api/routes.py`

- 后端内存维护 `sessions: dict[str, SessionData]`
- `SessionData` 包含：`session_id`, `messages: list[dict]`, `files: list[dict]`, `created_at`, `last_active`
- 新增端点：
  - `POST /api/sessions` — 创建新会话，返回 session_id
  - `GET /api/sessions/{session_id}` — 获取会话信息和历史消息
  - `DELETE /api/sessions/{session_id}` — 删除会话
  - `POST /api/sessions/{session_id}/messages` — 发送消息（SSE 响应）
  - `POST /api/sessions/{session_id}/files` — 上传文件到会话
- 保留 `POST /api/agent/run` 作为兼容端点（内部创建临时 session）

### 2.2 SSE Streaming

**修改文件**: `backend/app/api/routes.py` + `backend/app/api/sse.py`（新建）

- `POST /api/sessions/{session_id}/messages` 返回 `text/event-stream`
- 事件类型：
  - `event: text` — LLM 文本输出（增量）
  - `event: tool_call` — Agent 调用工具 `{name, arguments}`
  - `event: tool_result` — 工具返回结果 `{name, result}`
  - `event: debug` — 调试信息 `{step, request_messages, response, usage, duration_ms}`
  - `event: done` — 任务完成 `{success, message}`
  - `event: error` — 错误 `{message}`
- 使用 asyncio Queue 实现：agent_loop 每产生一个事件就 put，SSE generator get 后发送

### 2.3 Debug 数据传递

- agent_loop 内部维护 `debug_log: list[dict]`
- 每次 LLM 交互记录完整的 request messages + response + usage + duration
- 通过 SSE `event: debug` 实时推送到前端
- 最终的 debug_log 也包含在会话的 metadata 中，前端可通过 GET 接口获取完整历史

### 2.4 请求/响应格式更新

**修改文件**: `backend/app/api/schemas.py`

- 新增 `ChatMessage` schema：`{role, content, tool_calls?, tool_call_id?}`
- 新增 `SessionCreateResponse`：`{session_id}`
- 修改 `AgentRunResponse`：增加 `session_id`、`messages`、`debug_log` 字段
- 保留旧字段的兼容

---

## Phase 3：清理删除

### 3.1 删除文件

| 文件/目录 | 原因 |
|-----------|------|
| `agent/nodes/plan.py` | 被 agent_loop 替代 |
| `agent/nodes/execute.py` | 被 agent_loop 替代 |
| `agent/nodes/verify.py` | LLM 自行验证 |
| `agent/nodes/replan.py` | LLM 自行调整策略 |
| `agent/nodes/finalize.py` | agent_loop 结束即 finalize |
| `agent/nodes/__init__.py` | 目录清空 |
| `agent/tools/all_tools.py` | 被 tools.py 替代 |
| `agent/tools/base.py` | 被 tools.py 替代 |
| `agent/tools/__init__.py` | 被 tools.py 替代 |
| `agent/graph.py` | 被 loop.py 替代 |
| `application/agent_service.py` | 被 routes.py 中的 session 逻辑替代 |
| `domain/action_types.py` | 不再需要 ActionType 枚举 |
| `domain/task_config.py` | 不再需要关键词推断 |
| `domain/capability_types.py` | 不再需要 CapabilityType 枚举 |
| `domain/target_selector.py` | 由 LLM 自行决定 |
| `domain/field_config.py` | 由 LLM 自行决定 |
| `domain/output_schema.py` | 简化响应格式 |
| `domain/models.py` | 大幅简化 |
| `mcp/` 整个目录 | 死代码 |

### 3.2 保留文件

| 文件/目录 | 原因 |
|-----------|------|
| `document/` 整个目录 | Word/Excel/PDF/PPT 读写能力是核心资产 |
| `core/llm_client.py` | 保留 + 扩展 |
| `core/config.py` | 配置保留 |
| `core/file_store.py` | 文件管理保留 |
| `core/logger.py` | 日志保留 |
| `api/file_uploads.py` | 文件上传保留 |
| `api/translator.py` | 工具函数保留 |

---

## 实施顺序

1. `core/llm_client.py` — 增加 `chat_with_tools()` + `LLMResponse`
2. `agent/tools.py` — 新建 ToolRegistry + 注册所有工具
3. `agent/sandbox.py` — 新建 execute_code 沙箱
4. `agent/state.py` — 简化为 messages + files + metadata
5. `agent/prompts.py` — 重写 system prompt
6. `agent/loop.py` — 新建 ReAct 循环
7. `api/sse.py` — 新建 SSE 工具函数
8. `api/schemas.py` — 更新请求/响应 schema
9. `api/routes.py` — 增加 session 端点 + SSE 响应
10. 删除 Phase 3 中列出的所有文件
11. `main.py` — 适配新路由
