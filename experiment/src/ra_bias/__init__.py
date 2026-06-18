"""Core package for Reflection-as-Bias experiments."""

from .agent_loop import AgentConfig, ResearchAgentLoop
from .bias_engine import (
    BiasEngine,
    HardPruningBiasEngine,
    HeuristicLLMBiasEngine,
    NoBiasEngine,
    SoftTagBiasEngine,
    WeakTagBiasEngine,
)
from .environment import SimulatedResearchEnvironment
from .models import (
    BudgetUsage,
    Candidate,
    EpisodeLog,
    Outcome,
    ReflectionSignal,
    RoundLog,
    RoundState,
    Task,
)
from .reflection import SimpleReflector
from .selector import SelectionConfig, Selector
from .strategies import (
    CandidateStrategy,
    SinglePathStrategy,
    TextualReflectionBranchingStrategy,
    TopKBranchingStrategy,
)

__all__ = [
    "AgentConfig",
    "BiasEngine",
    "BudgetUsage",
    "Candidate",
    "CandidateStrategy",
    "EpisodeLog",
    "HardPruningBiasEngine",
    "HeuristicLLMBiasEngine",
    "NoBiasEngine",
    "Outcome",
    "ReflectionSignal",
    "ResearchAgentLoop",
    "RoundLog",
    "RoundState",
    "SelectionConfig",
    "Selector",
    "SimpleReflector",
    "SimulatedResearchEnvironment",
    "SinglePathStrategy",
    "SoftTagBiasEngine",
    "Task",
    "TextualReflectionBranchingStrategy",
    "TopKBranchingStrategy",
    "WeakTagBiasEngine",
]
