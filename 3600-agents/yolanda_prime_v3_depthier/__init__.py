from __future__ import annotations

__all__ = [
    "PlayerAgent",
    "BeliefEngine",
    "RuntimeState",
    "TimeManager",
    "Orchestrator",
]


def __getattr__(name: str):
    if name == "PlayerAgent":
        from .agent import PlayerAgent

        return PlayerAgent
    if name == "BeliefEngine":
        from .tracking.belief import BeliefEngine

        return BeliefEngine
    if name == "RuntimeState":
        from .infra.runtime_state import RuntimeState

        return RuntimeState
    if name == "TimeManager":
        from .infra.time_manager import TimeManager

        return TimeManager
    if name == "Orchestrator":
        from .strategy.orchestrator import Orchestrator

        return Orchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
