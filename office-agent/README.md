# Office Agent

一个基于 FastAPI 的文档智能处理服务。支持通过自然语言对 Office/文本文档进行读取、提取、定位、填充、比较、校验与输出，并提供简易前端页面用于调试。

## 功能概览

- 多文档处理：支持上传单文件或多文件任务。
- 智能任务路由：支持 `auto` 推断任务类型，也可手动指定。
- 可控响应粒度：支持 `full`、`summary`、`minimal` 三种输出模式。
- 结构化输出：统一返回 `result_text`、`result_files`、`structured_data`、`execution_trace`。
- 内置前端：启动后可直接在浏览器提交 prompt 与文件。

## 目录结构

```text
office-agent/
├─ backend/
│  ├─ run.py                 # 后端启动入口
│  ├─ requirements.txt       # Python 依赖
│  └─ app/
│     ├─ main.py             # FastAPI 应用
│     ├─ api/                # HTTP 接口
│     ├─ agent/              # 规划/执行/验证运行时
│     ├─ document/           # 文档能力层
│     ├─ domain/             # 领域模型与输出 schema
│     └─ core/               # 配置、日志、LLM 客户端等
├─ frontend/                 # 调试页面（由后端静态托管）
└─ storage/                  # 上传、输出、缓存目录
```

## 环境要求

- Python 3.10+
- 建议使用 Conda 或 venv
- Windows / macOS / Linux

## 快速开始

### 1. 安装依赖

在项目根目录执行：

```bash
cd backend
pip install -r requirements.txt
```

如果提示缺少 `pydantic_settings`，可额外安装：

```bash
pip install pydantic-settings
```

### 2. 配置环境变量（可选但推荐）

在 `backend` 目录创建 `.env`，常用配置如下：

```env
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=deepseek-chat
LLM_TIMEOUT=120

LOG_LEVEL=INFO
LOG_FORMAT=json
```

说明：未配置 LLM 密钥时，系统会尽量以降级模式运行，但效果会受限。

### 3. 启动服务

```bash
cd backend
python run.py
```

默认会优先尝试端口 `8000`，若占用则回退到 `8010`、`8020`。

启动成功后可访问：

- `http://127.0.0.1:8000/`：前端页面（端口以实际输出为准）
- `http://127.0.0.1:8000/docs`：OpenAPI 文档
- `http://127.0.0.1:8000/ui`：静态前端入口

## API 使用

### 1) 表单上传接口

`POST /api/agent/run`

表单字段：

- `prompt`：用户指令（必填）
- `files`：上传文件（可多文件）
- `capabilities`：JSON 字符串（可选）
- `output_mode`：`full|summary|minimal`
- `task_type`：`auto|summarize|fill|extract|compare|validate|...`
- `infer_task_type`：`true|false`
- `include_execution_logs`：`true|false`

Windows PowerShell 5.1 推荐示例（使用 `curl.exe`）：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/agent/run" ^
	-F "prompt=请总结这份文档的主要结论" ^
	-F "files=@E:/office-agent/storage/uploads/test_summary_input.txt" ^
	-F "output_mode=summary" ^
	-F "task_type=auto" ^
	-F "infer_task_type=true" ^
	-F "include_execution_logs=false"
```

### 2) JSON 接口

`POST /api/agent/run_json`

请求示例：

```json
{
	"prompt": "请提取关键信息并给出摘要",
	"task_mode": "auto",
	"files": [
		{
			"file_id": "f1",
			"filename": "test_summary_input.txt",
			"path": "storage/uploads/test_summary_input.txt"
		}
	],
	"capabilities": {},
	"output_mode": "summary",
	"task_type": "auto",
	"infer_task_type": true,
	"include_execution_logs": false
}
```

### 返回字段

- `success`：是否成功
- `result_text`：主文本结果
- `result_files`：生成文件列表
- `structured_data`：结构化结果（如 checks/issues）
- `execution_trace`：执行轨迹
- `answer`、`result`：兼容字段

## 常见问题

### `python run.py` 启动失败

可按顺序排查：

1. 确认当前环境已安装 `backend/requirements.txt` 中依赖。
2. 确认 Python 环境正确激活（如 `conda activate agent`）。
3. 端口冲突时查看启动日志实际端口（可能切到 `8010` 或 `8020`）。
4. 若报模块缺失，按错误提示执行 `pip install <module>`。

### 上传后无结果文件

- 检查 `storage/outputs` 是否有写权限。
- 将 `include_execution_logs=true` 并使用 `output_mode=full` 查看详细轨迹。

## 开发建议

- 调试接口优先使用 `/docs`。
- 前端仅用于联调与演示，核心能力在 `backend/app`。
- 提交新能力时，建议同步更新 `api/schemas.py` 与本 README 的“API 使用”章节。

## License

当前仓库未声明开源许可证。如需开源，请补充 `LICENSE` 文件。

## Backend Retry Tuning

You can tune runtime retries with these `.env` values:

```env
AGENT_MAX_REPLANS=2
AGENT_MAX_STEP_RETRIES=1
AGENT_RETRY_BACKOFF_BASE_SECONDS=0.8
AGENT_RETRY_BACKOFF_MAX_SECONDS=5.0
AGENT_RETRY_BACKOFF_JITTER_SECONDS=0.2
```

Safety rule: mutating actions (`fill`, `write`, `update_table`) are not auto-retried by default.
If a step is idempotent and safe to repeat, set step param `retry_mutating=true`.

Additional trace payload limits:

```env
AGENT_TRACE_MAX_STRING_CHARS=2000
AGENT_TRACE_MAX_COLLECTION_ITEMS=50
```
