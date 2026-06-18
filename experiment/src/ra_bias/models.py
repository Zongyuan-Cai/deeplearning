from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Task:
    task_id: str
    description: str
    candidate_pool: list[dict[str, Any]]
    initial_state: dict[str, Any] = field(default_factory=dict)
    candidate_generation_rule: str = "sample_from_pool"
    success_rule: str = "outcome.success"
    budget_max_rounds: int = 6
    budget_max_tokens: int = 8_000


@dataclass
class Candidate:
    candidate_id: str
    description: str
    tags: list[str]
    base_score: float = 0.0
    bias_score: float = 0.0
    final_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Outcome:
    success: bool
    quality_score: float
    score: float
    failure_modes: list[str]
    cost_tokens: int
    cost_steps: int = 1
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReflectionSignal:
    prefer_tags: list[str] = field(default_factory=list)
    avoid_tags: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    confidence: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RoundState:
    task_id: str
    round_idx: int
    budget_tokens_left: int
    budget_steps_left: int
    history: list[dict[str, Any]]
    exposed_failure_modes: list[str]


@dataclass
class BudgetUsage:
    tokens_used: int
    tokens_left: int
    steps_used: int
    steps_left: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RoundLog:
    task_id: str
    round_idx: int
    method_name: str
    candidate_set: list[dict[str, Any]]
    ranking_before: list[str]
    ranking_after: list[str]
    selected_candidate: dict[str, Any]
    outcome: dict[str, Any]
    score: float
    best_score: float
    reflection_signal: dict[str, Any]
    bias_before: dict[str, Any]
    bias_after: dict[str, Any]
    budget_usage: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EpisodeLog:
    task_id: str
    method_name: str
    rounds: list[RoundLog]
    success: bool
    steps: int
    total_tokens: int
    terminated_by: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "method_name": self.method_name,
            "rounds": [r.to_dict() for r in self.rounds],
            "success": self.success,
            "steps": self.steps,
            "total_tokens": self.total_tokens,
            "terminated_by": self.terminated_by,
        }
