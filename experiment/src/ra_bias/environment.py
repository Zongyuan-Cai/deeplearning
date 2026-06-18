from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Candidate, Outcome, Task


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass
class SimulatedResearchEnvironment:
    """Controllable research-like environment for iterative decision experiments."""

    seed: int = 7
    base_cost_tokens: int = 320

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    def get_candidate_pool(self, task: Task, round_idx: int) -> list[Candidate]:
        if not task.candidate_pool:
            raise ValueError(f"Task {task.task_id} has empty candidate pool.")

        candidates: list[Candidate] = []
        for idx, item in enumerate(task.candidate_pool):
            base = float(item.get("base_score", 0.5))
            noisy_base = _clamp(base + self.rng.uniform(-0.05, 0.05))
            cid = str(item.get("id", f"cand_{idx}"))
            candidates.append(
                Candidate(
                    candidate_id=f"{cid}_r{round_idx}_{idx}",
                    description=str(item.get("description", cid)),
                    tags=list(item.get("tags", [])),
                    base_score=noisy_base,
                    metadata={
                        "hidden_quality": float(item.get("hidden_quality", 0.5)),
                        "failure_modes": list(item.get("failure_modes", ["unknown_failure"])),
                    },
                )
            )
        return candidates

    def execute(self, task: Task, candidate: Candidate) -> Outcome:
        hidden_quality = float(candidate.metadata.get("hidden_quality", 0.5))

        # Non-linear map: high-quality candidates become much more likely to succeed.
        success_prob = _clamp(0.02 + 0.94 * (hidden_quality**2))
        success = self.rng.random() < success_prob

        quality = _clamp(hidden_quality + self.rng.uniform(-0.1, 0.1))
        if success:
            quality = max(quality, 0.62)
            failure_modes: list[str] = []
        else:
            quality = min(quality, 0.58)
            failure_modes = list(candidate.metadata.get("failure_modes", ["execution_failed"]))

        token_cost = self.base_cost_tokens + self.rng.randint(80, 220) + 20 * len(candidate.tags)

        return Outcome(
            success=success,
            quality_score=quality,
            score=quality,
            failure_modes=failure_modes,
            cost_tokens=token_cost,
            cost_steps=1,
            notes=f"Task={task.task_id}; candidate={candidate.description}",
        )


def build_demo_tasks() -> list[Task]:
    return [
        Task(
            task_id="task_reasoning_1",
            description="Find a robust strategy for a difficult reasoning subproblem.",
            candidate_generation_rule="fixed_pool",
            budget_max_rounds=6,
            budget_max_tokens=8000,
            candidate_pool=[
                {
                    "id": "single_pass",
                    "description": "single-pass prompting",
                    "tags": ["single_pass", "prompt_only"],
                    "base_score": 0.74,
                    "hidden_quality": 0.25,
                    "failure_modes": ["fragile_reasoning", "hallucination"],
                },
                {
                    "id": "decompose_verify",
                    "description": "decomposition + verification",
                    "tags": ["multi_step", "verification"],
                    "base_score": 0.60,
                    "hidden_quality": 0.86,
                    "failure_modes": ["verification_gap"],
                },
                {
                    "id": "search_verify",
                    "description": "search + verification",
                    "tags": ["search", "verification"],
                    "base_score": 0.56,
                    "hidden_quality": 0.74,
                    "failure_modes": ["retrieval_noise"],
                },
                {
                    "id": "tree_search",
                    "description": "tree search planning",
                    "tags": ["tree_search", "multi_step"],
                    "base_score": 0.54,
                    "hidden_quality": 0.68,
                    "failure_modes": ["branch_explosion"],
                },
            ],
        ),
        Task(
            task_id="task_planning_1",
            description="Choose the most reliable planning route under uncertain constraints.",
            candidate_generation_rule="fixed_pool",
            budget_max_rounds=6,
            budget_max_tokens=8000,
            candidate_pool=[
                {
                    "id": "fast_plan",
                    "description": "fast heuristic planning",
                    "tags": ["single_pass", "heuristic"],
                    "base_score": 0.71,
                    "hidden_quality": 0.28,
                    "failure_modes": ["constraint_violation"],
                },
                {
                    "id": "verify_plan",
                    "description": "plan + intermediate verification",
                    "tags": ["verification", "multi_step"],
                    "base_score": 0.62,
                    "hidden_quality": 0.84,
                    "failure_modes": ["partial_verification"],
                },
                {
                    "id": "retrieve_plan",
                    "description": "retrieval-augmented planning",
                    "tags": ["search", "retrieval"],
                    "base_score": 0.58,
                    "hidden_quality": 0.72,
                    "failure_modes": ["stale_evidence"],
                },
                {
                    "id": "tree_plan",
                    "description": "tree-of-thought planning",
                    "tags": ["tree_search", "multi_step"],
                    "base_score": 0.55,
                    "hidden_quality": 0.7,
                    "failure_modes": ["branch_explosion"],
                },
            ],
        ),
        Task(
            task_id="task_verification_1",
            description="Find a verification-heavy route that maximizes robustness.",
            candidate_generation_rule="fixed_pool",
            budget_max_rounds=6,
            budget_max_tokens=8000,
            candidate_pool=[
                {
                    "id": "direct_answer",
                    "description": "direct answer then self-check",
                    "tags": ["single_pass", "self_check"],
                    "base_score": 0.73,
                    "hidden_quality": 0.27,
                    "failure_modes": ["self_check_overfit"],
                },
                {
                    "id": "multi_verify",
                    "description": "multi-step solve + verification",
                    "tags": ["multi_step", "verification"],
                    "base_score": 0.61,
                    "hidden_quality": 0.85,
                    "failure_modes": ["verification_gap"],
                },
                {
                    "id": "retrieve_verify",
                    "description": "retrieve evidence + verification",
                    "tags": ["retrieval", "verification"],
                    "base_score": 0.57,
                    "hidden_quality": 0.76,
                    "failure_modes": ["evidence_noise"],
                },
                {
                    "id": "debate_verify",
                    "description": "multi-agent debate + verification",
                    "tags": ["debate", "verification"],
                    "base_score": 0.53,
                    "hidden_quality": 0.67,
                    "failure_modes": ["debate_drift"],
                },
            ],
        ),
    ]
