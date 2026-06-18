from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.runtime import AgentRuntime
from app.document.service import DocumentService


def _make_paths(root: Path) -> dict[str, Path]:
    cache = root / "storage" / "cache" / "smoke_multi"
    return {
        "word1": cache / "sample_word_1.docx",
        "word2": cache / "sample_word_2.docx",
        "excel1": cache / "sample_excel_1.xlsx",
        "excel2": cache / "sample_excel_2.xlsx",
        "pdf1": cache / "sample_pdf_1.pdf",
        "ppt1": cache / "sample_ppt_1.pptx",
        "txt1": root / "storage" / "uploads" / "test_summary_input.txt",
    }


def _summary(result) -> dict[str, Any]:
    data = result.data if isinstance(result.data, dict) else {}
    return {
        "success": bool(result.success),
        "message": result.message,
        "has_output": bool(result.output_path),
        "data_keys": sorted(list(data.keys()))[:12],
    }


def run_document_smoke(root: Path) -> dict[str, Any]:
    files = _make_paths(root)
    svc = DocumentService()
    out: dict[str, Any] = {}

    out["word.read"] = _summary(svc.read_document(str(files["word1"])))
    out["word.extract"] = _summary(svc.extract_fields(str(files["word1"])))
    out["word.fill"] = _summary(svc.fill_document(str(files["word1"]), field_values={"name": "Alice"}))
    out["word.write"] = _summary(svc.write_document(str(files["word1"]), append_text="smoke append"))
    out["word.compare"] = _summary(
        svc.compare_documents(left_file_path=str(files["word1"]), right_file_path=str(files["word2"]))
    )
    out["word.validate"] = _summary(svc.validate_document(str(files["word1"])))

    out["excel.read"] = _summary(svc.read_document(str(files["excel1"])))
    out["excel.extract"] = _summary(svc.extract_fields(str(files["excel1"])))
    out["excel.fill"] = _summary(svc.fill_document(str(files["excel1"]), cell_values={"B2": "Alice"}))
    out["excel.update_table"] = _summary(
        svc.update_table(str(files["excel1"]), headers=[" Name "], rows=[{" Name ": "Bob"}])
    )
    out["excel.compare"] = _summary(
        svc.compare_documents(left_file_path=str(files["excel1"]), right_file_path=str(files["excel2"]))
    )
    out["excel.validate"] = _summary(svc.validate_document(str(files["excel1"]), required_cells=["A1"]))

    out["pdf.read"] = _summary(svc.read_document(str(files["pdf1"])))
    out["pdf.extract"] = _summary(svc.extract_fields(str(files["pdf1"])))
    out["pdf.write"] = _summary(svc.write_document(str(files["pdf1"])))
    out["pdf.validate"] = _summary(svc.validate_document(str(files["pdf1"])))

    out["ppt.read"] = _summary(svc.read_document(str(files["ppt1"])))
    out["ppt.extract"] = _summary(svc.extract_fields(str(files["ppt1"])))
    out["ppt.fill"] = _summary(svc.fill_document(str(files["ppt1"]), field_values={"title": "Smoke"}))
    out["ppt.write"] = _summary(svc.write_document(str(files["ppt1"])))
    out["ppt.validate"] = _summary(svc.validate_document(str(files["ppt1"])))

    out["text.read"] = _summary(svc.read_document(str(files["txt1"])))
    out["text.extract"] = _summary(svc.extract_fields(str(files["txt1"])))
    out["text.fill"] = _summary(svc.fill_document(str(files["txt1"]), field_values={"name": "Alice"}))
    out["text.compare"] = _summary(
        svc.compare_documents(left_file_path=str(files["txt1"]), right_file_path=str(files["txt1"]))
    )
    out["text.write"] = _summary(svc.write_document(str(files["txt1"]), text="hello", write_mode="append"))
    out["text.validate"] = _summary(svc.validate_document(str(files["txt1"])))
    return out


def run_agent_smoke(root: Path) -> dict[str, Any]:
    files = _make_paths(root)
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
    final_output = result.get("final_output", {}) if isinstance(result, dict) else {}
    return {
        "success": bool(result.get("success", False)),
        "summary": (result.get("summary") or {}).get("summary"),
        "issues": (result.get("summary") or {}).get("issues", []),
        "output_files": len(final_output.get("files", []) if isinstance(final_output, dict) else []),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    document_checks = run_document_smoke(root)
    agent_check = run_agent_smoke(root)

    all_items = list(document_checks.values()) + [agent_check]
    ok = sum(1 for item in all_items if item.get("success"))
    total = len(all_items)
    failed = total - ok
    result = {
        "total": total,
        "ok": ok,
        "failed": failed,
        "document_checks": document_checks,
        "agent_check": agent_check,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
