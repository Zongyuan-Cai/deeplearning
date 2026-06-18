from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .evaluation import Metrics
from .models import EpisodeLog


def _select_case_episode(episodes: list[EpisodeLog]) -> EpisodeLog | None:
    # Prefer a successful multi-round trajectory for qualitative analysis.
    ranked = sorted(episodes, key=lambda e: (not e.success, e.steps == 1, -e.steps))
    return ranked[0] if ranked else None


def build_analysis_artifacts(
    metrics_list: list[Metrics],
    episodes_by_method: dict[str, list[EpisodeLog]],
    output_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    main_table = []
    quality_trends = {}
    score_curves = {}
    best_so_far_curves = {}
    bias_evolution = {}
    for m in metrics_list:
        main_table.append(
            {
                "method": m.method_name,
                "final_best_score": m.final_best_score,
                "avg_best_score": m.avg_best_score,
                "success_rate": m.success_rate,
                "avg_steps_to_success": m.avg_steps_to_success,
                "rounds_to_threshold": m.rounds_to_threshold,
                "best_score_under_budget": m.best_score_under_budget,
                "wasted_exploration_ratio": m.wasted_exploration_ratio,
                "cost_per_success": m.cost_per_success,
                "ranking_shift": m.ranking_shift,
            }
        )
        quality_trends[m.method_name] = m.candidate_quality_trend
        score_curves[m.method_name] = m.score_curve
        best_so_far_curves[m.method_name] = m.best_so_far_curve

    for method, episodes in episodes_by_method.items():
        by_round_conf: dict[int, list[float]] = {}
        for ep in episodes:
            for r in ep.rounds:
                ridx = int(r.round_idx)
                conf = float(r.bias_after.get("confidence", 0.0))
                by_round_conf.setdefault(ridx, []).append(conf)
        bias_evolution[method] = {
            r: (sum(vals) / len(vals) if vals else 0.0)
            for r, vals in sorted(by_round_conf.items(), key=lambda x: x[0])
        }

    case_studies = {}
    for method, eps in episodes_by_method.items():
        case = _select_case_episode(eps)
        if case is not None:
            case_studies[method] = case.to_dict()

    artifacts = {
        "main_table": output_dir / "analysis_main_table.json",
        "quality_trends": output_dir / "analysis_quality_trends.json",
        "score_curves": output_dir / "analysis_score_curves.json",
        "best_so_far_curves": output_dir / "analysis_best_so_far_curves.json",
        "bias_evolution": output_dir / "analysis_bias_evolution.json",
        "case_studies": output_dir / "analysis_case_studies.json",
    }

    with artifacts["main_table"].open("w", encoding="utf-8") as f:
        json.dump(main_table, f, ensure_ascii=False, indent=2)

    with artifacts["quality_trends"].open("w", encoding="utf-8") as f:
        json.dump(quality_trends, f, ensure_ascii=False, indent=2)

    with artifacts["score_curves"].open("w", encoding="utf-8") as f:
        json.dump(score_curves, f, ensure_ascii=False, indent=2)

    with artifacts["best_so_far_curves"].open("w", encoding="utf-8") as f:
        json.dump(best_so_far_curves, f, ensure_ascii=False, indent=2)

    with artifacts["bias_evolution"].open("w", encoding="utf-8") as f:
        json.dump(bias_evolution, f, ensure_ascii=False, indent=2)

    with artifacts["case_studies"].open("w", encoding="utf-8") as f:
        json.dump(case_studies, f, ensure_ascii=False, indent=2)

    return {k: str(v) for k, v in artifacts.items()}
