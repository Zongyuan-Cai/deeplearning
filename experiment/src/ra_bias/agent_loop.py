from __future__ import annotations

from dataclasses import dataclass

from .bias_engine import BiasEngine
from .environment import SimulatedResearchEnvironment
from .models import (
    BudgetUsage,
    EpisodeLog,
    Outcome,
    ReflectionSignal,
    RoundLog,
    RoundState,
    Task,
)
from .reflection import SimpleReflector
from .selector import Selector
from .strategies import CandidateStrategy


def _check_success(task: Task, outcome: Outcome) -> bool:
    rule = task.success_rule.strip().lower()
    if rule == "outcome.success":
        return bool(outcome.success)

    if rule.startswith("quality>="):
        threshold = float(rule.split("quality>=", 1)[1])
        return outcome.quality_score >= threshold

    if rule.startswith("quality>"):
        threshold = float(rule.split("quality>", 1)[1])
        return outcome.quality_score > threshold

    # Fallback to explicit success field.
    return bool(outcome.success)


@dataclass
class AgentConfig:
    method_name: str
    max_rounds: int | None = None
    budget_tokens: int | None = None
    enable_reflection: bool = True
    enable_bias: bool = True


@dataclass
class ResearchAgentLoop:
    env: SimulatedResearchEnvironment
    strategy: CandidateStrategy
    reflector: SimpleReflector
    bias_engine: BiasEngine
    selector: Selector
    cfg: AgentConfig

    def run(self, task: Task) -> EpisodeLog:
        max_rounds = self.cfg.max_rounds if self.cfg.max_rounds is not None else task.budget_max_rounds
        budget_tokens_left = self.cfg.budget_tokens if self.cfg.budget_tokens is not None else task.budget_max_tokens
        budget_steps_left = max_rounds

        round_logs: list[RoundLog] = []
        history: list[dict[str, object]] = []
        signal = ReflectionSignal()
        exposed_failure_modes: set[str] = set()
        best_score_so_far = 0.0

        success = False
        terminated_by = "max_rounds"

        for round_idx in range(1, max_rounds + 1):
            if budget_tokens_left <= 0:
                terminated_by = "budget"
                break
            if budget_steps_left <= 0:
                terminated_by = "max_rounds"
                break

            pre_state = RoundState(
                task_id=task.task_id,
                round_idx=round_idx,
                budget_tokens_left=budget_tokens_left,
                budget_steps_left=budget_steps_left,
                history=list(history),
                exposed_failure_modes=sorted(exposed_failure_modes),
            )

            candidate_pool = self.env.get_candidate_pool(task, round_idx=round_idx)
            candidate_set = self.strategy.generate(candidate_pool, pre_state, signal)
            if not candidate_set:
                terminated_by = "empty_candidate_set"
                break

            ranking_before = self.selector.rank_by_base(candidate_set)
            bias_before = signal.to_dict()

            if self.cfg.enable_bias:
                bias_scores = self.bias_engine.score(candidate_set, signal)
            else:
                bias_scores = {c.candidate_id: 0.0 for c in candidate_set}

            self.selector.apply_scores(candidate_set, bias_scores)
            ranking_after = self.selector.rank_by_final(candidate_set)

            selected = self.selector.select(candidate_set)
            outcome = self.env.execute(task, selected)
            round_success = _check_success(task, outcome)

            budget_tokens_left -= outcome.cost_tokens
            budget_steps_left -= outcome.cost_steps

            exposed_failure_modes.update(outcome.failure_modes)

            post_state = RoundState(
                task_id=task.task_id,
                round_idx=round_idx,
                budget_tokens_left=budget_tokens_left,
                budget_steps_left=budget_steps_left,
                history=list(history),
                exposed_failure_modes=sorted(exposed_failure_modes),
            )

            if self.cfg.enable_reflection:
                new_signal = self.reflector.reflect(post_state, outcome, selected.tags)
            else:
                new_signal = ReflectionSignal(notes="Reflection disabled.")

            best_score_so_far = max(best_score_so_far, outcome.score)

            round_logs.append(
                RoundLog(
                    task_id=task.task_id,
                    round_idx=round_idx,
                    method_name=self.cfg.method_name,
                    candidate_set=[c.to_dict() for c in candidate_set],
                    ranking_before=ranking_before,
                    ranking_after=ranking_after,
                    selected_candidate=selected.to_dict(),
                    outcome=outcome.to_dict(),
                    score=outcome.score,
                    best_score=best_score_so_far,
                    reflection_signal=new_signal.to_dict(),
                    bias_before=bias_before,
                    bias_after=new_signal.to_dict(),
                    budget_usage=BudgetUsage(
                        tokens_used=outcome.cost_tokens,
                        tokens_left=budget_tokens_left,
                        steps_used=outcome.cost_steps,
                        steps_left=budget_steps_left,
                    ).to_dict(),
                )
            )

            history.append(
                {
                    "round": round_idx,
                    "selected": selected.description,
                    "success": round_success,
                    "quality": round(outcome.quality_score, 4),
                    "failure_modes": list(outcome.failure_modes),
                }
            )

            signal = new_signal
            if round_success:
                success = True
                terminated_by = "success"
                break

        total_tokens = sum(r.outcome["cost_tokens"] for r in round_logs)
        if not round_logs and terminated_by == "max_rounds":
            terminated_by = "empty_run"

        return EpisodeLog(
            task_id=task.task_id,
            method_name=self.cfg.method_name,
            rounds=round_logs,
            success=success,
            steps=len(round_logs),
            total_tokens=total_tokens,
            terminated_by=terminated_by,
        )
