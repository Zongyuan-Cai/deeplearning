from __future__ import annotations

import json
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.agent.runtime import AgentRuntime
from app.main import app


def _paths(root: Path) -> dict[str, Path]:
    cache = root / "storage" / "cache" / "smoke_multi"
    return {
        "word1": cache / "sample_word_1.docx",
        "excel1": cache / "sample_excel_1.xlsx",
        "txt1": root / "storage" / "uploads" / "test_summary_input.txt",
    }


def _check_runtime_lifecycle(root: Path) -> dict:
    files = _paths(root)
    input_files = [
        {"file_id": "f_word", "filename": files["word1"].name, "path": str(files["word1"])},
        {"file_id": "f_excel", "filename": files["excel1"].name, "path": str(files["excel1"])},
    ]
    file_map = {item["file_id"]: item for item in input_files}
    runtime = AgentRuntime(file_resolver=lambda file_id: file_map[file_id])
    result = runtime.run(
        user_request="Fill the Word template using the Excel data and produce an output file.",
        files=input_files,
        capabilities={"allow_fallback": True, "task_type": "fill"},
    )
    lifecycle = result.get("lifecycle", {}) if isinstance(result, dict) else {}
    return {
        "success": bool(result.get("success", False)),
        "has_attempts": isinstance(lifecycle.get("attempts"), int),
        "has_termination_reason": isinstance(lifecycle.get("termination_reason"), str),
        "has_iteration_history": isinstance(lifecycle.get("iteration_history"), list),
    }


def _check_api_execution_fields(root: Path) -> dict:
    files = _paths(root)
    client = TestClient(app)
    payload = {
        "prompt": "Please summarize the content.",
        "task_mode": "auto",
        "files": [{"file_id": "f1", "filename": files["txt1"].name, "path": str(files["txt1"])}],
        "capabilities": {"allow_fallback": True},
        "output_mode": "full",
        "task_type": "summarize",
        "infer_task_type": True,
        "include_execution_logs": True,
    }
    resp = client.post("/api/agent/run_json", json=payload)
    body = resp.json()
    execution = body.get("result", {}).get("payload", {}).get("execution", {})
    return {
        "status_code": resp.status_code,
        "success": bool(body.get("success", False)),
        "has_attempts": isinstance(execution.get("attempts"), int),
        "has_termination_reason": isinstance(execution.get("termination_reason"), str),
        "has_iteration_history": isinstance(execution.get("iteration_history"), list),
    }


def main() -> None:
    root = BACKEND_ROOT
    runtime_check = _check_runtime_lifecycle(root)
    api_check = _check_api_execution_fields(root)
    ok = (
        runtime_check.get("success", False)
        and runtime_check.get("has_attempts", False)
        and runtime_check.get("has_termination_reason", False)
        and runtime_check.get("has_iteration_history", False)
        and api_check.get("status_code") == 200
        and api_check.get("success", False)
        and api_check.get("has_attempts", False)
        and api_check.get("has_termination_reason", False)
        and api_check.get("has_iteration_history", False)
    )
    output = {
        "ok": ok,
        "checks": {
            "runtime_lifecycle": runtime_check,
            "api_execution": api_check,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
