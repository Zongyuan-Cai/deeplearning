from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Candidate, ReflectionSignal, RoundState


class CandidateStrategy:
    """Defines which candidates are exposed to the selector in each round."""

    def generate(
        self,
        candidate_pool: list[Candidate],
        round_state: RoundState,
        reflection_signal: ReflectionSignal,
    ) -> list[Candidate]:
        raise NotImplementedError


@dataclass
class RandomStrategy(CandidateStrategy):
    """Random baseline: expose a random subset each round."""

    top_k: int = 4

    def generate(
        self,
        candidate_pool: list[Candidate],
        round_state: RoundState,
        reflection_signal: ReflectionSignal,
    ) -> list[Candidate]:
        if not candidate_pool:
            return []
        count = min(self.top_k, len(candidate_pool))
        seed = sum(ord(ch) for ch in round_state.task_id) + 97 * round_state.round_idx + 13 * len(candidate_pool)
        rng = random.Random(seed)
        return rng.sample(candidate_pool, k=count)


@dataclass
class SinglePathStrategy(CandidateStrategy):
    """Single-path baseline: expose only one best-by-base candidate."""

    def generate(
        self,
        candidate_pool: list[Candidate],
        round_state: RoundState,
        reflection_signal: ReflectionSignal,
    ) -> list[Candidate]:
        if not candidate_pool:
            return []
        return [max(candidate_pool, key=lambda c: c.base_score)]


@dataclass
class TopKBranchingStrategy(CandidateStrategy):
    top_k: int = 4

    def generate(
        self,
        candidate_pool: list[Candidate],
        round_state: RoundState,
        reflection_signal: ReflectionSignal,
    ) -> list[Candidate]:
        if not candidate_pool:
            return []
        ranked = sorted(candidate_pool, key=lambda c: c.base_score, reverse=True)
        return ranked[: min(self.top_k, len(ranked))]


@dataclass
class TextualReflectionBranchingStrategy(TopKBranchingStrategy):
    """Baseline with textual reflection retained as metadata, not as bias."""

    def generate(
        self,
        candidate_pool: list[Candidate],
        round_state: RoundState,
        reflection_signal: ReflectionSignal,
    ) -> list[Candidate]:
        selected = super().generate(candidate_pool, round_state, reflection_signal)
        notes = reflection_signal.notes.strip()
        if notes:
            for c in selected:
                c.metadata["textual_reflection_context"] = notes
        return selected
