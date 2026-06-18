from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Candidate


@dataclass
class SelectionConfig:
    alpha: float = 1.0
    mode: str = "greedy"  # greedy | sample


class Selector:
    def __init__(self, cfg: SelectionConfig) -> None:
        self.cfg = cfg

    @staticmethod
    def rank_by_base(candidates: list[Candidate]) -> list[str]:
        ranked = sorted(candidates, key=lambda c: c.base_score, reverse=True)
        return [c.candidate_id for c in ranked]

    @staticmethod
    def rank_by_final(candidates: list[Candidate]) -> list[str]:
        ranked = sorted(candidates, key=lambda c: c.final_score, reverse=True)
        return [c.candidate_id for c in ranked]

    def apply_scores(self, candidates: list[Candidate], bias_scores: dict[str, float]) -> list[Candidate]:
        for c in candidates:
            c.bias_score = float(bias_scores.get(c.candidate_id, 0.0))
            c.final_score = c.base_score + self.cfg.alpha * c.bias_score
        return candidates

    def select(self, candidates: list[Candidate]) -> Candidate:
        if not candidates:
            raise ValueError("No candidates available for selection.")

        if self.cfg.mode == "sample":
            return self._sample(candidates)
        return max(candidates, key=lambda c: c.final_score)

    def _sample(self, candidates: list[Candidate]) -> Candidate:
        min_score = min(c.final_score for c in candidates)
        shifted = [c.final_score - min_score + 1e-6 for c in candidates]
        total = sum(shifted)
        p = random.random() * total
        acc = 0.0
        for c, w in zip(candidates, shifted):
            acc += w
            if acc >= p:
                return c
        return candidates[-1]
