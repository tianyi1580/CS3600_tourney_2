from __future__ import annotations

__all__ = [
    "PlayerAgent",
    "BeliefEngine",
    "PolicyEngine",
    "RuntimeState",
    "TimeManager",
]


def __getattr__(name: str):
    if name == "PlayerAgent":
        from .agent import PlayerAgent

        return PlayerAgent
    if name == "BeliefEngine":
        from .tracking.belief import BeliefEngine

        return BeliefEngine
    if name == "PolicyEngine":
        from .strategy.policy import PolicyEngine

        return PolicyEngine
    if name == "RuntimeState":
        from .infra.runtime_state import RuntimeState

        return RuntimeState
    if name == "TimeManager":
        from .infra.time_manager import TimeManager

        return TimeManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
