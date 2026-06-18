# Office Agent — 系统架构文档

## 1. 概述

Office Agent 是一个基于 FastAPI 的文档智能处理服务。用户通过自然语言描述意图，系统自动完成文档读取、信息提取、字段填充、内容比较、校验与输出等操作。支持 Word、Excel、PDF、PPT、纯文本等文档格式。

**技术栈：** Python 3.10+ / FastAPI / Pydantic / OpenAI-compatible LLM / python-docx / openpyxl / python-pptx / pypdf

---

## 2. 项目结构

```
office-agent/
├── backend/                    # 后端服务（核心）
│   ├── run.py                  # 启动入口（uvicorn）
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # FastAPI 应用工厂
│       ├── api/                # HTTP 接口层
│       ├── application/        # 应用服务层（编排）
│       ├── agent/              # Agent 运行时（规划→执行→验证）
│       │   ├── action_handlers/# 动作处理器
│       │   ├── routing/        # 路由与注册
│       │   ├── schemas/        # 内部数据模型
│       │   └── policies/       # 策略（重试/重规划等）
│       ├── document/           # 文档能力层
│       │   ├── providers/      # 文档格式提供者（Word/Excel/PDF/PPT/Text）
│       │   ├── word/           # Word 专项能力模块
│       │   └── excel/          # Excel 专项能力模块
│       ├── domain/             # 领域模型与类型定义
│       ├── core/               # 基础设施（配置/LLM客户端/存储）
│       ├── mcp/                # MCP 工具服务
│       └── utils/              # 工具函数
├── frontend/                   # 调试用前端页面（静态托管）
└── storage/                    # 运行时存储（上传/输出/缓存）
```

---

## 3. 分层架构

系统采用经典的四层架构，自上而下为：

```
┌─────────────────────────────────────────┐
│  API 层  (app/api/)                     │  ← HTTP 接口 / 参数校验 / 响应封装
├─────────────────────────────────────────┤
│  应用层  (app/application/)             │  ← 编排：组装参数 → 启动 Runtime → 规范化输出
├─────────────────────────────────────────┤
│  Agent 层 (app/agent/)                  │  ← 核心：规划 → 执行 → 验证 → 重规划 循环
├─────────────────────────────────────────┤
│  文档层  (app/document/)                │  ← 能力：文档路由 → 格式提供者 → 具体操作
├─────────────────────────────────────────┤
│  领域层  (app/domain/)                  │  ← 共享：枚举 / 模型 / 类型推断
├─────────────────────────────────────────┤
│  基础设施 (app/core/)                   │  ← LLM客户端 / 配置 / 文件存储 / 日志
└─────────────────────────────────────────┘
```

### 3.1 各层职责

| 层 | 目录 | 核心职责 |
|---|---|---|
| API | `app/api/` | 接收 HTTP 请求、文件上传、参数解析、响应封装 |
| Application | `app/application/` | 组装 AgentRunOptions、启动 AgentRuntime、应用输出偏好 |
| Agent | `app/agent/` | 规划→执行→验证→重规划 主循环，状态管理，动作派发 |
| Document | `app/document/` | 统一文档能力接口，格式路由，各格式专项实现 |
| Domain | `app/domain/` | 动作类型、文档类型、能力类型枚举，领域模型，任务推断 |
| Core | `app/core/` | LLM 客户端（带重试/结构化输出）、配置管理、文件存储 |

---

## 4. 核心流程

### 4.1 请求处理全链路

```
HTTP POST /api/agent/run
    │
    ▼
routes.py                    ← 解析表单/JSON，持久化上传文件
    │
    ▼
AgentApplicationService      ← 规范化参数、推断任务类型、构建能力配置
    │
    ▼
AgentRuntime.run()           ← 核心执行入口
    │
    ├── 1. 创建 Session       (AgentSession)
    ├── 2. 初始化 Memory      (WorkingMemory)
    ├── 3. 构建 Workflow      (WorkflowContext)
    ├── 4. PlannerV2 生成计划  (ActionPlan)
    ├── 5. PlanSanitizer 清洗  (合法性校验)
    ├── 6. AgentLoop 执行循环
    │       ├── Executor 逐步执行
    │       ├── Verifier 验证结果
    │       └── Replanner 失败重规划
    └── 7. Finalizer 封装输出  (AgentResultModel)
    │
    ▼
presenter.py                 ← 构建统一 API 响应
```

### 4.2 Agent 循环详解

```
AgentLoop.run_with_plan()
    │
    loop:
    │
    ├── Executor.execute_plan(plan)
    │   │
    │   └── for step in plan.steps:
    │       ├── check_dependencies()        ← 前置步骤是否成功
    │       ├── CapabilityResolver          ← 解析步骤路由
    │       ├── ActionHandlerRegistry       ← 查找处理器
    │       └── handler.handle()            ← 执行，失败则按策略重试
    │           │
    │           └── DocumentService.xxx()   ← 调用文档层能力
    │
    ├── Verifier.summarize()                ← 确定性检查 + LLM 总结
    │
    ├── if verified → 返回成功
    │
    └── if failed and can_replan:
        ├── Replanner.rebuild_plan()        ← 规则修补 / LLM 重规划
        └── 继续循环（最多 max_replans 次）
```

---

## 5. Agent 层详解

### 5.1 规划器 (PlannerV2)

**文件：** `app/agent/planner_v2.py`

- **LLM 驱动规划：** 将用户请求、文件列表、能力配置发送给 LLM，生成 `ActionPlan`
- **Planning Contract：** 根据推断的任务类型限制 `allowed_actions`，控制 LLM 输出范围
- **Fallback 规划：** 当 LLM 不可用或输出无效时，使用规则生成计划：
  - Excel→Word 填表：scan_template → extract → (build_mapping) → fill → write
  - 单文件摘要：read → summarize
  - 单文件提取：extract

**任务类型 → 允许动作映射（lean 模式）：**

| 任务类型 | 允许的动作 |
|---------|-----------|
| summarize | read, summarize |
| extract | read, extract |
| fill / scan_template | read, extract, fill, write, scan_template, locate, validate |
| compare | read, compare, summarize |
| validate | read, validate |
| update_table | read, extract, update_table, write |

### 5.2 执行器 (Executor)

**文件：** `app/agent/executor.py`

- **逐步执行：** 按 ActionPlan 步骤顺序执行，检查依赖关系
- **失败分类：**
  - `retryable` — 超时、限流、网络错误 → 自动重试
  - `replannable` — 无处理器、不支持的能力、依赖失败 → 触发重规划
  - `non_recoverable` — 无效输入、文件不存在 → 立即终止
- **重试策略：** 指数退避 + 随机抖动，可通过 `.env` 配置
- **安全规则：** 写操作（fill, write, update_table）默认不自动重试，需显式 `retry_mutating=true`

### 5.3 动作处理器 (Action Handlers)

**目录：** `app/agent/action_handlers/`

每个处理器对应一个动作类型，负责将 Agent Step 翻译为 DocumentService 调用：

| 处理器 | 动作类型 | 调用的服务方法 |
|--------|---------|--------------|
| ReadDocumentHandler | read | DocumentService.read_document() |
| ExtractStructuredDataHandler | extract | DocumentService.extract_fields() |
| FillFieldsHandler | fill | DocumentService.fill_document() |
| WriteOutputHandler | write | DocumentService.write_document() |
| SummarizeContentHandler | summarize | DocumentService.summarize_document() |
| CompareDocumentsHandler | compare | DocumentService.compare_documents() |
| LocateTargetsHandler | locate | DocumentService.locate_targets() |
| ScanTemplateFieldsHandler | scan_template | DocumentService.scan_template() |
| UpdateTableHandler | update_table | DocumentService.update_table() |
| ValidateOutputHandler | validate | DocumentService.validate_document() |
| BuildFieldMappingHandler | build_field_mapping | LLMClient.match_source_to_template() |

**FillFieldsHandler 的智能推断：** 当没有显式提供 `field_values` 时，会自动从 ExecutionContext 中推断：
1. 检查 artifacts（显式生成的映射产物）
2. 从 intermediate_refs 收集模板字段和源数据
3. 通过键名规范化对齐模板字段与源数据

### 5.4 验证器 (Verifier)

**文件：** `app/agent/verifier.py`

两层验证策略：

1. **确定性检查（始终执行）：**
   - 步骤执行成功性
   - 字段完整性（无 None/空字符串）
   - 模板填充完整性
   - 输出文件存在性与非空
   - 摘要非空检查
   - 映射非空检查

2. **LLM 辅助总结（可选，依赖 LLM 可用性）：**
   - 在确定性结果基础上生成更丰富的总结

### 5.5 重规划器 (Replanner)

**文件：** `app/agent/replan.py`

双层重规划策略：

1. **规则修补（优先）：** 基于失败动作类型直接修改计划：
   - `extract` 失败 → 前置 `read` 步骤，降级为粗粒度模式
   - `locate` 失败 → 切换为全文搜索模式
   - `fill` 失败（多字段）→ 拆分为逐字段填充

2. **LLM 重规划（备用）：** 将旧计划和执行轨迹发送给 LLM 生成新计划

### 5.6 状态管理

**ExecutionContext / ExecutionState：** (`app/agent/schemas/action.py`)
- 持有所有步骤的观察结果 (`observations`)
- 持有中间产物引用 (`intermediate_refs`)：read_documents, extracted_fields, generated_mappings 等
- 持有显式产出的 artifacts
- 支持按步骤 ID 查询和依赖校验

**WorkingMemory：** (`app/agent/memory.py`)
- 文件清单与角色分配
- 文档文本/结构/表格视图缓存
- 提取字段与候选映射
- 输出文件追踪

---

## 6. 文档层详解

### 6.1 架构

```
DocumentService (统一入口)
    │
    ▼
DocumentRouter (格式路由)
    │
    ├── detect_document_type()  ← 扩展名 + 魔数探测
    │
    ▼
CapabilityRegistry (能力注册表)
    │
    ├── DocumentType → Provider 映射
    └── DocumentType → 能力矩阵
    │
    ▼
Provider (格式提供者)
    │
    ├── WordProvider    → word/* 模块
    ├── ExcelProvider   → excel/* 模块
    ├── PdfProvider     → pypdf 封装
    ├── PptProvider     → python-pptx 封装
    └── TextProvider    → 纯文本读写
```

### 6.2 能力矩阵

| 能力 | Word | Excel | PDF | PPT | Text |
|------|------|-------|-----|-----|------|
| read | ✓ | ✓ | ✓ | ✓ | ✓ |
| extract | ✓ | ✓ | ✓ | ✓ | ✓ |
| locate | ✓ | ✓ | ✓ | ✓ | ✓ |
| fill | ✓ | ✓ | ✓ | ✓ | ✓ |
| validate | ✓ | ✓ | ✓ | ✓ | ✓ |
| write | ✓ | ✓ | ✓ | ✓ | ✓ |
| compare | ✓ | ✓ | — | — | ✓ |
| update_table | — | ✓ | — | — | — |
| scan_template | ✓ | — | ✓ | ✓ | ✓ |
| summarize | — | — | ✓ | ✓ | ✓ |

### 6.3 启动引导

**文件：** `app/document/bootstrap.py`

`bootstrap_document_providers()` 在首次调用 `AgentApplicationService.execute()` 时执行：
1. 注册能力矩阵到 `CapabilityRegistry`
2. 实例化并注册所有 Provider（Word/Excel/PDF/PPT/Text）

采用幂等设计，多次调用仅执行一次。

### 6.4 Word 专项能力模块

**目录：** `app/document/word/`

| 模块 | 功能 |
|------|------|
| parser.py | 段落/表格读取，结构提取 |
| analyzer.py | 占位符发现、标题层级分析、表格结构分析、语义字段归一化 |
| locator.py | 文本搜索定位 |
| filler.py | 键值对填充到模板 |
| writer.py | 文本替换/追加 |
| validator.py | 填充结果验证 |
| comparator.py | 文档差异比较 |
| template_scanner.py | 模板占位符扫描 |

**占位符识别：** 支持三种模式 `{{field}}`、`<<field>>`、`【field】`，在段落、表格、页眉页脚中全局搜索。

### 6.5 ProviderResult 统一返回模型

**文件：** `app/document/providers/base.py`

```python
class ProviderResult(BaseModel):
    success: bool          # 操作是否成功
    message: str           # 人类可读描述
    error_code: str | None # 错误码（便于分类处理）
    capability: str | None # 所属能力
    provider: str | None   # 提供者名称
    document_type: str | None
    data: dict             # 结构化数据
    output_path: str | None# 输出文件路径（write/fill 操作）
    raw: dict              # 原始响应
```

---

## 7. API 层

### 7.1 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 前端页面 |
| GET | `/docs` | OpenAPI 文档 |
| POST | `/api/agent/run` | 表单上传（multipart/form-data） |
| POST | `/api/agent/run_json` | JSON 请求体 |

### 7.2 输出模式

| 模式 | 说明 |
|------|------|
| `full` | 完整输出（默认）：trace, observations, memory, context 全部返回 |
| `summary` | 摘要输出：移除 trace, observations, memory, context |
| `minimal` | 最小输出：仅返回 success, session, summary, execution, final_output |

### 7.3 统一响应格式

```json
{
  "success": true,
  "result_text": "文本结果",
  "result_files": [{"path": "...", "filename": "..."}],
  "structured_data": {"checks": {...}, "issues": [...]},
  "execution_trace": [{"step_id": "...", "success": true, ...}]
}
```

---

## 8. 领域类型系统

### 8.1 动作类型 (ActionType)

**文件：** `app/domain/action_types.py`

| 枚举值 | 规范名 | 说明 |
|--------|--------|------|
| READ_DOCUMENT | read | 读取文档内容 |
| EXTRACT_STRUCTURED_DATA | extract | 提取结构化信息 |
| LOCATE_TARGETS | locate | 定位目标内容 |
| FILL_FIELDS | fill | 填充模板字段 |
| UPDATE_TABLE | update_table | 更新表格数据 |
| SUMMARIZE_CONTENT | summarize | 生成摘要 |
| COMPARE_DOCUMENTS | compare | 比较文档差异 |
| VALIDATE_OUTPUT | validate | 验证输出质量 |
| CREATE_OUTPUT | write | 写入输出文件 |
| BUILD_FIELD_MAPPING | build_field_mapping | 构建字段映射 |
| SCAN_TEMPLATE_FIELDS | scan_template | 扫描模板占位符 |

### 8.2 文档类型 (DocumentType)

**文件：** `app/domain/document_types.py`

- `word`, `excel`, `ppt`, `pdf`, `text`, `unknown`
- 探测策略：扩展名映射 → 别名匹配 → 文件头魔数 → ZIP 内部结构

### 8.3 能力类型 (CapabilityType)

**文件：** `app/domain/capability_types.py`

- `read`, `extract`, `locate`, `fill`, `update_table`, `summarize`, `compare`, `validate`, `write`, `scan_template`

---

## 9. MCP 层

**目录：** `app/mcp/`

MCP（Model Context Protocol）工具服务层，提供独立的工具协议接口：

- **MCPServerRegistry** — 服务注册与工具发现
- **LocalMCPClient** — 本地 MCP 客户端
- **MCP Servers：**
  - `document_server.py` — 通用文档操作
  - `word_server.py` — Word 专项工具（read_text, read_tables, extract_structure, replace_text, append_text）
  - `excel_server.py` — Excel 专项工具
  - `file_server.py` — 文件管理
  - `understanding_server.py` — 文档理解

---

## 10. 基础设施层

### 10.1 LLM 客户端

**文件：** `app/core/llm_client.py`

- 兼容 OpenAI API 协议
- 支持 `chat()`（纯文本）、`chat_json()`（JSON mode）、`chat_structured()`（JSON Schema）
- 自动重试（可配置次数和退避策略）
- 错误分类：AUTH / RATE_LIMIT / TIMEOUT / NETWORK / SERVER / BAD_RESPONSE / PARSE
- 高级帮助方法：`summarize_text()`, `extract_fields()`, `match_source_to_template()`, `finalize_response()`, `critique_step_failure()`
- 支持 thinking/reasoning 配置

### 10.2 配置管理

**文件：** `app/core/config.py`

使用 pydantic-settings，支持 `.env` 文件和环境变量。关键配置项：

- **LLM：** API_KEY, BASE_URL, MODEL, TIMEOUT, TEMPERATURE
- **Agent 运行时：** MAX_REPLANS (2), MAX_STEP_RETRIES (1), 退避参数
- **Trace：** 字符串截断长度 (2000), 集合条目上限 (50)
- **文件系统：** UPLOAD_DIR, OUTPUT_DIR, TEMP_DIR, CACHE_DIR

### 10.3 文件存储

**文件：** `app/core/file_store.py`

- 上传文件管理（按 task_id 隔离）
- 输出文件路径生成（时间戳 / 序列号命名）
- 临时文件管理
- JSON 缓存读写
- 过期文件自动清理（基于 TTL）

---

## 11. 前端

**目录：** `frontend/`

简易调试页面，包含：
- `index.html` — 表单界面（prompt 输入、文件上传、参数配置）
- `app.js` — 前端逻辑（表单提交、结果展示）
- `style.css` — 样式

由 FastAPI 通过 `StaticFiles` 静态托管在 `/ui` 路径。

---

## 12. 数据流图

```
                        ┌──────────────────┐
用户请求 ──────────────→│  API Routes      │
  (prompt + files)      │  /api/agent/run  │
                        └────────┬─────────┘
                                 │ AgentRunOptions
                        ┌────────▼─────────┐
                        │ Application      │
                        │ Service          │ ← 规范化、任务推断
                        └────────┬─────────┘
                                 │
                        ┌────────▼─────────┐
                        │ AgentRuntime     │
                        │                  │
                        │  Session ──┐     │
                        │  Memory ←──┤     │
                        │  Workflow  │     │
                        │            │     │
                        │  ┌─────────▼───┐ │
                        │  │ PlannerV2   │ │ ← LLM / Fallback
                        │  │ PlanSanitizer│ │
                        │  └─────┬───────┘ │
                        │        │ ActionPlan
                        │  ┌─────▼───────┐ │
                        │  │ AgentLoop   │ │
                        │  │             │ │
                        │  │ Executor ───┤─┼──→ ActionHandlers
                        │  │   ↓         │ │        │
                        │  │ Verifier    │ │   ┌────▼────────┐
                        │  │   ↓         │ │   │ Document     │
                        │  │ Replanner   │ │   │ Service      │
                        │  └─────┬───────┘ │   │   │          │
                        │        │         │   │ DocumentRouter│
                        │  ┌─────▼───────┐ │   │   │          │
                        │  │ Finalizer   │ │   │ Provider     │
                        │  └─────────────┘ │   └──────────────┘
                        └────────┬─────────┘
                                 │ AgentResultModel
                        ┌────────▼─────────┐
                        │ Presenter        │ ← 响应适配
                        └────────┬─────────┘
                                 │ AgentRunResponse
                        ┌────────▼─────────┐
                        │ HTTP Response    │
                        └──────────────────┘
```

---

## 13. 设计要点

### 13.1 LLM 降级策略

系统在 LLM 不可用或输出无效时自动降级为规则驱动：
- 规划器 Fallback：根据文件类型组合生成步骤链
- 验证器降级：仅执行确定性检查
- 重规划器降级：使用规则修补（extract→read, locate→full_text, fill→field_by_field）

### 13.2 安全写保护

变更操作（fill, write, update_table）默认不自动重试，避免重复写入导致的数据问题。仅在步骤显式设置 `retry_mutating=true` 时允许。

### 13.3 输出命名策略

支持两种命名模式：
- `timestamp`：`filename_20260101_120000.docx`
- `sequence`：`filename_001.docx`, `filename_002.docx`

### 13.4 输出模式灵活度

三种输出粒度（full/summary/minimal）让调用方按需控制响应大小，适用于调试、生产、和前端展示等不同场景。

### 13.5 扩展性

- 新增文档格式：继承 `BaseDocumentProvider`，注册到 `bootstrap.py`
- 新增动作类型：在 `ActionType` 枚举中添加，实现对应的 `ActionHandler`，在 `ActionHandlerRegistry` 注册
- 新增能力：在 `CapabilityType` 枚举中添加，在 Provider 中实现对应方法
