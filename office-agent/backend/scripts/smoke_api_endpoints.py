from __future__ import annotations

import json
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.main import app


def _paths(root: Path) -> dict[str, Path]:
    cache = root / "storage" / "cache" / "smoke_multi"
    return {
        "word1": cache / "sample_word_1.docx",
        "excel1": cache / "sample_excel_1.xlsx",
        "txt1": root / "storage" / "uploads" / "test_summary_input.txt",
    }


def main() -> None:
    root = BACKEND_ROOT
    files = _paths(root)

    client = TestClient(app)

    results: dict[str, dict] = {}

    # 1) JSON endpoint: excel -> word fill flow
    run_json_payload = {
        "prompt": "Fill word template using excel data.",
        "task_mode": "fill",
        "files": [
            {"file_id": "f_word", "filename": files["word1"].name, "path": str(files["word1"])},
            {"file_id": "f_excel", "filename": files["excel1"].name, "path": str(files["excel1"])},
        ],
        "capabilities": {"allow_fallback": True},
        "output_mode": "summary",
        "task_type": "fill",
        "infer_task_type": True,
        "include_execution_logs": False,
    }
    resp_json = client.post("/api/agent/run_json", json=run_json_payload)
    data_json = resp_json.json()
    results["run_json"] = {
        "status_code": resp_json.status_code,
        "success": bool(data_json.get("success", False)),
        "result_files": len(data_json.get("result_files", [])),
    }

    # 2) multipart endpoint: summarize text
    with open(files["txt1"], "rb") as f:
        resp_form = client.post(
            "/api/agent/run",
            data={
                "prompt": "Please summarize the content.",
                "capabilities": json.dumps({"allow_fallback": True}),
                "output_mode": "summary",
                "task_type": "summarize",
                "infer_task_type": "true",
                "include_execution_logs": "false",
            },
            files=[("files", (files["txt1"].name, f, "text/plain"))],
        )
    data_form = resp_form.json()
    results["run_form"] = {
        "status_code": resp_form.status_code,
        "success": bool(data_form.get("success", False)),
        "result_text_non_empty": bool(str(data_form.get("result_text", "")).strip()),
    }

    ok = all(
        item["status_code"] == 200 and item["success"] is True
        for item in results.values()
    )
    output = {"ok": ok, "results": results}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
