"""最终输出节点：组装与 Finalizer 兼容的结果结构。"""

from app.agent.state import AgentState


def finalize_node(state: AgentState) -> dict:
    step_results = state.get("step_results", {})
    verification = state.get("verification", {})
    intermediate_refs = state.get("intermediate_refs", {})
    trace = state.get("trace", [])
    plan_steps = state.get("plan_steps", [])
    replan_count = state.get("replan_count", 0)
    termination_reason = state.get("termination_reason", "")

    results = list(step_results.values())
    success = all(r.get("success", False) for r in results) if results else verification.get("success", False)

    # 收集输出文件
    output_files: list[dict] = []
    out_paths = intermediate_refs.get("output_file_paths", [])
    if isinstance(out_paths, list):
        for p in out_paths:
            if isinstance(p, str) and p:
                output_files.append({"path": p, "filename": p.rsplit("/", 1)[-1] if "/" in p else p.rsplit("\\", 1)[-1]})

    # 从 step_results 中找 produced_files
    for r in results:
        for pf in r.get("produced_files", []) or []:
            if isinstance(pf, str) and pf:
                entry = {"path": pf, "filename": pf.rsplit("/", 1)[-1] if "/" in p else pf.rsplit("\\", 1)[-1]}
                if entry not in output_files:
                    output_files.append(entry)

    # 构建文本结果
    text_result = "Task execution completed."
    for r in reversed(results):
        data = r.get("data", {})
        if isinstance(data, dict):
            summary = data.get("summary")
            if isinstance(summary, str) and summary.strip():
                text_result = summary.strip()
                break
    if verification.get("summary") and not text_result.strip():
        text_result = str(verification["summary"])

    # 构建结构化结果
    checks = verification.get("checks", {})
    issues = verification.get("issues", [])
    structured = {
        "success": success,
        "checks": checks,
        "issues": issues,
        "step_count": len(plan_steps),
        "observation_count": len(results),
        "lifecycle": {
            "replan_count": replan_count,
            "termination_reason": termination_reason,
        },
    }

    logs = {
        "trace": trace,
        "observation_logs": results,
        "lifecycle": {
            "replan_count": replan_count,
            "termination_reason": termination_reason,
        },
    }

    final_output = {
        "success": success,
        "session": {
            "task_id": "",
            "user_prompt": state.get("user_request", ""),
        },
        "plan": {"steps": plan_steps},
        "observations": results,
        "context": {"state": {"intermediate_refs": intermediate_refs, "files": state.get("files", [])}},
        "trace": trace,
        "summary": verification,
        "memory": {},
        "lifecycle": {"replan_count": replan_count, "termination_reason": termination_reason},
        "text_result": text_result,
        "file_result": output_files,
        "structured_result": structured,
        "logs": logs,
        "final_output": {
            "text": text_result,
            "files": output_files,
            "structured": structured,
            "logs": logs,
        },
    }

    return {
        "success": success,
        "final_output": final_output,
        "termination_reason": termination_reason or ("verified" if success else "exhausted"),
    }
