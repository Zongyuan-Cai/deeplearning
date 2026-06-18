from __future__ import annotations

from dataclasses import dataclass

from .models import EpisodeLog


@dataclass
class Metrics:
    method_name: str
    final_best_score: float
    avg_best_score: float
    success_rate: float
    avg_steps_to_success: float
    rounds_to_threshold: float
    best_score_under_budget: float
    wasted_exploration_ratio: float
    cost_per_success: float
    ranking_shift: float
    score_curve: dict[int, float]
    best_so_far_curve: dict[int, float]
    candidate_quality_trend: dict[int, float]


def compute_metrics(method_name: str, episodes: list[EpisodeLog]) -> Metrics:
    if not episodes:
        return Metrics(method_name, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {}, {}, {})

    success_episodes = [e for e in episodes if e.success]
    success_rate = len(success_episodes) / len(episodes)

    if success_episodes:
        avg_steps_to_success = sum(e.steps for e in success_episodes) / len(success_episodes)
        cost_per_success = sum(e.total_tokens for e in success_episodes) / len(success_episodes)
    else:
        avg_steps_to_success = 0.0
        cost_per_success = 0.0

    failed_trials = 0
    total_trials = 0
    rank_shifts: list[float] = []
    quality_by_round: dict[int, list[float]] = {}
    score_by_round: dict[int, list[float]] = {}
    best_by_round: dict[int, list[float]] = {}

    threshold = 0.8
    rounds_to_threshold_list: list[float] = []
    best_scores: list[float] = []

    for e in episodes:
        total_trials += e.steps
        reached_round = None
        ep_best = 0.0
        for r in e.rounds:
            if not r.outcome["success"]:
                failed_trials += 1

            selected_id = r.selected_candidate["candidate_id"]
            before = r.ranking_before
            after = r.ranking_after
            if selected_id in before and selected_id in after:
                rank_before = before.index(selected_id)
                rank_after = after.index(selected_id)
                rank_shifts.append(float(rank_before - rank_after))

            round_idx = int(r.round_idx)
            score = float(r.score)
            best_score = float(r.best_score)
            ep_best = max(ep_best, best_score)
            if reached_round is None and best_score >= threshold:
                reached_round = round_idx

            hidden_quality = float(r.selected_candidate.get("metadata", {}).get("hidden_quality", 0.0))
            quality_by_round.setdefault(round_idx, []).append(hidden_quality)
            score_by_round.setdefault(round_idx, []).append(score)
            best_by_round.setdefault(round_idx, []).append(best_score)

        best_scores.append(ep_best)
        rounds_to_threshold_list.append(float(reached_round if reached_round is not None else e.steps + 1))

    wasted_exploration_ratio = failed_trials / total_trials if total_trials else 0.0
    ranking_shift = sum(rank_shifts) / len(rank_shifts) if rank_shifts else 0.0
    final_best_score = max(best_scores) if best_scores else 0.0
    avg_best_score = sum(best_scores) / len(best_scores) if best_scores else 0.0
    rounds_to_threshold = (
        sum(rounds_to_threshold_list) / len(rounds_to_threshold_list) if rounds_to_threshold_list else 0.0
    )
    best_score_under_budget = avg_best_score

    candidate_quality_trend = {
        r: sum(vals) / len(vals)
        for r, vals in sorted(quality_by_round.items(), key=lambda x: x[0])
        if vals
    }
    score_curve = {
        r: sum(vals) / len(vals)
        for r, vals in sorted(score_by_round.items(), key=lambda x: x[0])
        if vals
    }
    best_so_far_curve = {
        r: sum(vals) / len(vals)
        for r, vals in sorted(best_by_round.items(), key=lambda x: x[0])
        if vals
    }

    return Metrics(
        method_name=method_name,
        final_best_score=final_best_score,
        avg_best_score=avg_best_score,
        success_rate=success_rate,
        avg_steps_to_success=avg_steps_to_success,
        rounds_to_threshold=rounds_to_threshold,
        best_score_under_budget=best_score_under_budget,
        wasted_exploration_ratio=wasted_exploration_ratio,
        cost_per_success=cost_per_success,
        ranking_shift=ranking_shift,
        score_curve=score_curve,
        best_so_far_curve=best_so_far_curve,
        candidate_quality_trend=candidate_quality_trend,
    )
