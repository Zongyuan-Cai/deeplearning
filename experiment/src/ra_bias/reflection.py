from __future__ import annotations

from dataclasses import dataclass

from .models import Outcome, ReflectionSignal, RoundState


@dataclass
class SimpleReflector:
    """Turns execution feedback into a structured reflection signal."""

    positive_threshold: float = 0.65
    negative_threshold: float = 0.35

    def reflect(self, round_state: RoundState, outcome: Outcome, selected_tags: list[str]) -> ReflectionSignal:
        if outcome.quality_score >= self.positive_threshold:
            confidence = min(1.0, 0.55 + 0.45 * outcome.quality_score)
            return ReflectionSignal(
                prefer_tags=list(selected_tags),
                avoid_tags=[],
                failure_modes=[],
                confidence=confidence,
                notes="Promote tags from this successful/high-quality attempt.",
            )

        if outcome.quality_score <= self.negative_threshold or not outcome.success:
            confidence = min(1.0, 0.55 + 0.45 * (1.0 - outcome.quality_score))
            return ReflectionSignal(
                prefer_tags=[],
                avoid_tags=list(selected_tags),
                failure_modes=list(outcome.failure_modes),
                confidence=confidence,
                notes="Downweight tags from this failed/low-quality attempt.",
            )

        return ReflectionSignal(
            prefer_tags=[],
            avoid_tags=[],
            failure_modes=list(outcome.failure_modes),
            confidence=0.2,
            notes="Ambiguous result; keep only weak adjustment.",
        )
