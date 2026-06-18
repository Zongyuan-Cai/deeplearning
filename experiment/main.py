from __future__ import annotations

import argparse

from src.ra_bias.evaluation import Metrics
from src.ra_bias.runner import CORE_METHODS, run_main_and_ablations


def format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def print_table(title: str, metrics: list[Metrics]) -> None:
    print(f"\n== {title} ==")
    print(
        "Method             FinalBest  AvgBest    Success Rate  Avg Steps  Rounds@0.8  "
        "Best@Budget  Cost/Success"
    )
    print("-" * 108)
    for m in metrics:
        print(
            f"{m.method_name:<18} {m.final_best_score:<10.3f} {m.avg_best_score:<10.3f} "
            f"{format_percent(m.success_rate):<13} {m.avg_steps_to_success:<10.2f} "
            f"{m.rounds_to_threshold:<11.2f} {m.best_score_under_budget:<12.3f} {m.cost_per_success:<12.1f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Reflection-as-Bias decision-framework experiments.")
    parser.add_argument(
        "--methods",
        nargs="+",
        default=CORE_METHODS,
        help="Methods to run for main experiment.",
    )
    parser.add_argument("--episodes", type=int, default=30, help="Number of episodes per method.")
    parser.add_argument("--output", type=str, default="outputs", help="Output directory for logs/analysis.")
    parser.add_argument("--no-ablation", action="store_true", help="Skip ablation experiments.")
    args = parser.parse_args()

    all_results = run_main_and_ablations(
        num_episodes=args.episodes,
        output_dir=args.output,
        run_ablation=not args.no_ablation,
    )

    main_metrics, main_artifacts = all_results["main"]
    if args.methods != CORE_METHODS:
        # Allow user-provided method override on main group.
        from src.ra_bias.runner import run_methods

        main_metrics, main_artifacts = run_methods(
            methods=args.methods,
            num_episodes=args.episodes,
            output_dir=f"{args.output}/main_custom",
        )

    print_table("Main Results", main_metrics)

    print("\nMain Analysis Artifacts")
    for name, path in main_artifacts.items():
        print(f"- {name}: {path}")

    for group_name, result in all_results.items():
        if group_name == "main":
            continue
        group_metrics, group_artifacts = result
        print_table(group_name, group_metrics)
        print(f"\n{group_name} Artifacts")
        for name, path in group_artifacts.items():
            print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
