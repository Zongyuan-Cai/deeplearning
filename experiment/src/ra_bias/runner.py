from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .agent_loop import AgentConfig, ResearchAgentLoop
from .analysis import build_analysis_artifacts
from .bias_engine import (
    HardPruningBiasEngine,
    HeuristicLLMBiasEngine,
    NoBiasEngine,
    ShuffledBiasEngine,
    SoftTagBiasEngine,
    StaticBiasEngine,
    WeakTagBiasEngine,
)
from .environment import SimulatedResearchEnvironment, build_demo_tasks
from .evaluation import Metrics, compute_metrics
from .logger import JsonlLogger
from .models import EpisodeLog, Task
from .reflection import SimpleReflector
from .selector import SelectionConfig, Selector
from .strategies import RandomStrategy, TextualReflectionBranchingStrategy, TopKBranchingStrategy


CORE_METHODS = ["random", "greedy", "reflection_only", "dynamic_bias"]
ABLATION_METHOD_GROUPS = {
    "ablation_no_reflection": ["dynamic_bias", "greedy"],
    "ablation_static_bias": ["dynamic_bias", "static_bias"],
    "ablation_shuffle_bias": ["dynamic_bias", "shuffled_bias"],
}


def build_agent(method: str, seed: int) -> ResearchAgentLoop:
    env = SimulatedResearchEnvironment(seed=seed)
    reflector = SimpleReflector()
    selector = Selector(SelectionConfig(alpha=1.0, mode="greedy"))

    if method in ("random", "single_path"):
        cfg = AgentConfig(method_name="random", enable_reflection=False, enable_bias=False)
        strategy = RandomStrategy(top_k=4)
        selector = Selector(SelectionConfig(alpha=1.0, mode="sample"))
        bias_engine = NoBiasEngine()

    elif method in ("greedy", "branching_only"):
        cfg = AgentConfig(method_name="greedy", enable_reflection=False, enable_bias=False)
        strategy = TopKBranchingStrategy(top_k=4)
        bias_engine = NoBiasEngine()

    elif method in ("reflection_only", "textual_reflection"):
        cfg = AgentConfig(method_name="reflection_only", enable_reflection=True, enable_bias=False)
        strategy = TextualReflectionBranchingStrategy(top_k=4)
        bias_engine = NoBiasEngine()

    elif method in ("dynamic_bias", "reflection_as_bias", "soft_bias"):
        cfg = AgentConfig(method_name="dynamic_bias", enable_reflection=True, enable_bias=True)
        strategy = TopKBranchingStrategy(top_k=4)
        bias_engine = SoftTagBiasEngine()

    elif method in ("hard_pruning",):
        cfg = AgentConfig(method_name=method, enable_reflection=True, enable_bias=True)
        strategy = TopKBranchingStrategy(top_k=4)
        bias_engine = HardPruningBiasEngine()

    elif method in ("weak_bias",):
        cfg = AgentConfig(method_name=method, enable_reflection=True, enable_bias=True)
        strategy = TopKBranchingStrategy(top_k=4)
        bias_engine = WeakTagBiasEngine()

    elif method in ("llm_bias",):
        cfg = AgentConfig(method_name=method, enable_reflection=True, enable_bias=True)
        strategy = TopKBranchingStrategy(top_k=4)
        bias_engine = HeuristicLLMBiasEngine()

    elif method in ("static_bias",):
        cfg = AgentConfig(method_name=method, enable_reflection=True, enable_bias=True)
        strategy = TopKBranchingStrategy(top_k=4)
        bias_engine = StaticBiasEngine()

    elif method in ("shuffled_bias",):
        cfg = AgentConfig(method_name=method, enable_reflection=True, enable_bias=True)
        strategy = TopKBranchingStrategy(top_k=4)
        bias_engine = ShuffledBiasEngine(seed=seed)

    else:
        raise ValueError(f"Unknown method: {method}")

    return ResearchAgentLoop(
        env=env,
        strategy=strategy,
        reflector=reflector,
        bias_engine=bias_engine,
        selector=selector,
        cfg=cfg,
    )


def expand_tasks(num_episodes: int) -> list[Task]:
    base_tasks = build_demo_tasks()
    tasks: list[Task] = []

    for ep_idx in range(num_episodes):
        t = base_tasks[ep_idx % len(base_tasks)]
        tasks.append(
            replace(
                t,
                task_id=f"{t.task_id}_ep{ep_idx+1}",
                initial_state={"episode_index": ep_idx + 1},
            )
        )
    return tasks


def run_method(method: str, num_episodes: int, base_seed: int = 7) -> tuple[list[EpisodeLog], Metrics]:
    tasks = expand_tasks(num_episodes)
    episodes: list[EpisodeLog] = []

    for idx, task in enumerate(tasks):
        # Same per-episode seed schedule across methods for fair comparison.
        agent = build_agent(method=method, seed=base_seed + idx)
        episodes.append(agent.run(task))

    method_name = episodes[0].method_name if episodes else method
    metrics = compute_metrics(method_name, episodes)
    return episodes, metrics


def run_methods(methods: list[str], num_episodes: int, output_dir: str) -> tuple[list[Metrics], dict[str, str]]:
    out = Path(output_dir)
    logger = JsonlLogger(output_dir=out)

    all_metrics: list[Metrics] = []
    all_episodes: list[EpisodeLog] = []
    episodes_by_method: dict[str, list[EpisodeLog]] = {}

    for method in methods:
        episodes, metrics = run_method(method=method, num_episodes=num_episodes)
        for ep in episodes:
            logger.write_episode(ep)
        all_episodes.extend(episodes)
        episodes_by_method[method] = episodes
        all_metrics.append(metrics)

    logger.write_summary(all_episodes, filename="all_methods_summary.json")
    artifacts = build_analysis_artifacts(all_metrics, episodes_by_method, out)

    return all_metrics, artifacts


def run_main_and_ablations(
    num_episodes: int,
    output_dir: str,
    run_ablation: bool = True,
) -> dict[str, tuple[list[Metrics], dict[str, str]]]:
    out = Path(output_dir)
    results: dict[str, tuple[list[Metrics], dict[str, str]]] = {}

    main_dir = out / "main"
    results["main"] = run_methods(methods=CORE_METHODS, num_episodes=num_episodes, output_dir=str(main_dir))

    if run_ablation:
        for group_name, methods in ABLATION_METHOD_GROUPS.items():
            group_dir = out / group_name
            results[group_name] = run_methods(methods=methods, num_episodes=num_episodes, output_dir=str(group_dir))

    return results
