"""LangGraph StateGraph 组装与编译。

图结构:
    START → plan → execute ⇄ verify → finalize → END
                    ↑        ↓
                    └─ replan ←┘
"""

from langgraph.graph import StateGraph, END

from app.agent.state import AgentState
from app.agent.nodes.plan import plan_node
from app.agent.nodes.execute import execute_node
from app.agent.nodes.verify import verify_node
from app.agent.nodes.replan import replan_node
from app.agent.nodes.finalize import finalize_node


def _after_plan(state: AgentState) -> str:
    steps = state.get("plan_steps", [])
    if not steps:
        return "finalize"
    return "execute"


def _after_execute(state: AgentState) -> str:
    steps = state.get("plan_steps", [])
    idx = state.get("current_step_index", 0)
    step_results = state.get("step_results", {})
    replan_count = state.get("replan_count", 0)
    max_replans = state.get("max_replans", 2)
    termination = state.get("termination_reason", "")

    # 获取当前步骤的结果
    if idx >= len(steps) and steps:
        # 所有步骤完成
        return "verify"
    if idx >= len(steps) and not steps:
        return "finalize"

    current_step = steps[idx] if idx < len(steps) else None
    if current_step is None:
        return "verify"

    step_id = current_step.get("id", "")
    result = step_results.get(step_id)

    if result is None:
        # 尚未执行（重规划后可能发生）
        return "execute"

    success = result.get("success", False)
    failure_reason = result.get("failure_reason", "")
    retry_count = state.get("retry_counts", {}).get(step_id, 0)
    max_retries = state.get("max_step_retries", 1)

    if success:
        if idx + 1 < len(steps):
            return "execute"
        return "verify"

    # 失败处理
    if failure_reason == "retryable" and retry_count < max_retries:
        return "execute"

    if failure_reason == "replannable" and replan_count < max_replans:
        return "replan"

    return "finalize"


def _after_verify(state: AgentState) -> str:
    verification = state.get("verification", {})
    replan_count = state.get("replan_count", 0)
    max_replans = state.get("max_replans", 2)

    if verification.get("success", False):
        return "finalize"

    if replan_count < max_replans:
        return "replan"

    return "finalize"


def build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("plan", plan_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("verify", verify_node)
    workflow.add_node("replan", replan_node)
    workflow.add_node("finalize", finalize_node)

    workflow.set_entry_point("plan")

    workflow.add_conditional_edges("plan", _after_plan, {
        "execute": "execute",
        "finalize": "finalize",
    })

    workflow.add_conditional_edges("execute", _after_execute, {
        "execute": "execute",
        "verify": "verify",
        "replan": "replan",
        "finalize": "finalize",
    })

    workflow.add_conditional_edges("verify", _after_verify, {
        "finalize": "finalize",
        "replan": "replan",
    })

    workflow.add_edge("replan", "execute")
    workflow.add_edge("finalize", END)

    return workflow.compile()


# 编译好的 graph 实例，供 application 层调用
agent_graph = build_graph()
