from __future__ import annotations

import random
from dataclasses import dataclass, field

from .models import Candidate, ReflectionSignal


class BiasEngine:
    """Interface: transform reflection signal into per-candidate bias scores."""

    def score(self, candidates: list[Candidate], signal: ReflectionSignal) -> dict[str, float]:
        raise NotImplementedError


@dataclass
class NoBiasEngine(BiasEngine):
    def score(self, candidates: list[Candidate], signal: ReflectionSignal) -> dict[str, float]:
        return {c.candidate_id: 0.0 for c in candidates}


@dataclass
class SoftTagBiasEngine(BiasEngine):
    """Soft bias: score adjustment without deleting candidates."""

    prefer_weight: float = 0.35
    avoid_weight: float = 0.45

    def score(self, candidates: list[Candidate], signal: ReflectionSignal) -> dict[str, float]:
        scores: dict[str, float] = {}
        confidence = max(0.0, min(1.0, signal.confidence))

        prefer = set(signal.prefer_tags)
        avoid = set(signal.avoid_tags)

        for c in candidates:
            overlap_prefer = len(prefer.intersection(c.tags))
            overlap_avoid = len(avoid.intersection(c.tags))
            bias = (self.prefer_weight * overlap_prefer - self.avoid_weight * overlap_avoid) * confidence
            scores[c.candidate_id] = bias
        return scores


@dataclass
class WeakTagBiasEngine(SoftTagBiasEngine):
    prefer_weight: float = 0.12
    avoid_weight: float = 0.15


@dataclass
class HardPruningBiasEngine(SoftTagBiasEngine):
    """Hard pruning: forbid avoided candidates via extreme penalty."""

    prune_penalty: float = -1_000_000.0

    def score(self, candidates: list[Candidate], signal: ReflectionSignal) -> dict[str, float]:
        base = super().score(candidates, signal)
        avoid = set(signal.avoid_tags)

        for c in candidates:
            if avoid.intersection(c.tags):
                base[c.candidate_id] = self.prune_penalty
        return base


@dataclass
class HeuristicLLMBiasEngine(BiasEngine):
    """LLM-based bias placeholder for offline experiments.

    This deterministic heuristic mimics semantic scoring without external API calls.
    """

    semantic_weight: float = 0.28

    def score(self, candidates: list[Candidate], signal: ReflectionSignal) -> dict[str, float]:
        confidence = max(0.0, min(1.0, signal.confidence))
        notes = signal.notes.lower()
        failure_tokens = {x.lower() for x in signal.failure_modes}

        scores: dict[str, float] = {}
        for c in candidates:
            tag_text = " ".join(c.tags).lower()
            desc = c.description.lower()

            # Semantic-like preference from reflection text.
            bonus = 0.0
            for t in signal.prefer_tags:
                if t.lower() in tag_text or t.lower() in desc:
                    bonus += self.semantic_weight
            for t in signal.avoid_tags:
                if t.lower() in tag_text or t.lower() in desc:
                    bonus -= self.semantic_weight

            # Penalize descriptions that echo observed failure patterns.
            for ft in failure_tokens:
                if ft and ft in desc:
                    bonus -= 0.12

            scores[c.candidate_id] = bonus * confidence
        return scores


@dataclass
class StaticBiasEngine(BiasEngine):
    """Freeze the first non-empty reflection signal, then reuse it across rounds."""

    base_engine: BiasEngine = field(default_factory=SoftTagBiasEngine)
    _frozen_signal: ReflectionSignal | None = None

    def score(self, candidates: list[Candidate], signal: ReflectionSignal) -> dict[str, float]:
        if self._frozen_signal is None and (signal.prefer_tags or signal.avoid_tags):
            self._frozen_signal = ReflectionSignal(
                prefer_tags=list(signal.prefer_tags),
                avoid_tags=list(signal.avoid_tags),
                failure_modes=list(signal.failure_modes),
                confidence=signal.confidence,
                notes=f"[frozen]{signal.notes}",
            )

        active_signal = self._frozen_signal if self._frozen_signal is not None else signal
        return self.base_engine.score(candidates, active_signal)


@dataclass
class ShuffledBiasEngine(BiasEngine):
    """Compute soft bias then randomly remap scores to wrong candidates."""

    base_engine: BiasEngine = field(default_factory=SoftTagBiasEngine)
    seed: int = 17

    def score(self, candidates: list[Candidate], signal: ReflectionSignal) -> dict[str, float]:
        raw_scores = self.base_engine.score(candidates, signal)
        ids = [c.candidate_id for c in candidates]
        values = [raw_scores[cid] for cid in ids]
        rng = random.Random(self.seed + len(ids) + int(signal.confidence * 1000))
        rng.shuffle(values)
        return {cid: val for cid, val in zip(ids, values)}
