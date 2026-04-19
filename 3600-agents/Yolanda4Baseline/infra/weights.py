from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class ParameterSpec:
    """Single tunable scalar surfaced to the offline optimizer."""

    name: str
    default: float
    minimum: float
    maximum: float
    tier: str


_SPECS: tuple[ParameterSpec, ...] = (
    # Tier A: high-sensitivity policy coefficients.
    ParameterSpec("a", 1.40, 0.5, 3.0, "A"),
    ParameterSpec("b", 0.45, 0.1, 1.5, "A"),
    ParameterSpec("c", 1.20, 0.3, 3.0, "A"),
    ParameterSpec("d", 0.35, 0.05, 1.5, "A"),
    ParameterSpec("f", 0.75, 0.2, 2.0, "A"),
    ParameterSpec("g", 0.50, 0.0, 1.5, "A"),
    ParameterSpec("opp_response_weight", 0.10, 0.0, 0.5, "A"),
    # Tier B: expectiminimax leaf evaluation.
    ParameterSpec("eval_potential_w", 0.55, 0.1, 1.5, "B"),
    ParameterSpec("eval_chain_w", 0.60, 0.1, 2.0, "B"),
    ParameterSpec("eval_exit_w", 0.35, 0.05, 1.0, "B"),
    ParameterSpec("eval_entry_adv_w", 0.30, 0.0, 1.0, "B"),
    ParameterSpec("eval_trap_w", 0.80, 0.1, 2.0, "B"),
    ParameterSpec("eval_rat_w", 0.35, 0.0, 1.0, "B"),
    # Tier C: rat opportunity signal.
    ParameterSpec("rat_nearby_w", 2.0, 0.5, 5.0, "C"),
    ParameterSpec("rat_peak_w", 3.0, 0.5, 8.0, "C"),
    ParameterSpec("rat_peak_thresh", 0.20, 0.05, 0.40, "C"),
    # Tier D: search-vs-move gate.
    ParameterSpec("farmable_ev_scale", 0.90, 0.5, 1.0, "D"),
    ParameterSpec("farmable_margin_base", 0.15, 0.0, 0.4, "D"),
    ParameterSpec("farmable_margin_slope", 0.20, 0.0, 0.5, "D"),
    ParameterSpec("nonfarm_margin_base", 0.25, 0.0, 0.5, "D"),
    ParameterSpec("nonfarm_margin_slope", 0.50, 0.1, 1.0, "D"),
    # Tier E: phase multipliers for score_non_search.
    ParameterSpec("opening_mult_a", 0.8, 0.2, 3.0, "E"),
    ParameterSpec("opening_mult_b", 1.0, 0.2, 3.0, "E"),
    ParameterSpec("opening_mult_c", 1.8, 0.2, 3.0, "E"),
    ParameterSpec("opening_mult_d", 0.4, 0.2, 3.0, "E"),
    ParameterSpec("opening_mult_f", 1.0, 0.2, 3.0, "E"),
    ParameterSpec("mid_mult_a", 1.0, 0.2, 3.0, "E"),
    ParameterSpec("mid_mult_b", 0.8, 0.2, 3.0, "E"),
    ParameterSpec("mid_mult_c", 1.5, 0.2, 3.0, "E"),
    ParameterSpec("mid_mult_d", 0.8, 0.2, 3.0, "E"),
    ParameterSpec("mid_mult_f", 1.0, 0.2, 3.0, "E"),
    ParameterSpec("late_mult_a", 1.5, 0.2, 3.0, "E"),
    ParameterSpec("late_mult_b", 0.3, 0.2, 3.0, "E"),
    ParameterSpec("late_mult_c", 0.5, 0.2, 3.0, "E"),
    ParameterSpec("late_mult_d", 1.2, 0.2, 3.0, "E"),
    ParameterSpec("late_mult_f", 0.5, 0.2, 3.0, "E"),
    # Tier F: extra time-allocation knobs. The design doc mentioned TimeManager
    # but never surfaced it; these stay optional so the documented 36-D search
    # space remains available unchanged.
    ParameterSpec("time_opening_multiplier", 1.80, 0.5, 3.0, "F"),
    ParameterSpec("time_mid_multiplier", 1.40, 0.5, 3.0, "F"),
    ParameterSpec("time_late_multiplier", 1.00, 0.5, 2.0, "F"),
    ParameterSpec("time_opening_cap", 8.0, 1.0, 12.0, "F"),
    ParameterSpec("time_mid_cap", 6.0, 1.0, 10.0, "F"),
    ParameterSpec("time_late_cap", 3.0, 0.5, 6.0, "F"),
)

SPECS_BY_NAME: dict[str, ParameterSpec] = {spec.name: spec for spec in _SPECS}
DEFAULTS: dict[str, float] = {spec.name: spec.default for spec in _SPECS}

PARAMETER_PROFILES: dict[str, tuple[str, ...]] = {
    "tier_ab": tuple(spec.name for spec in _SPECS if spec.tier in {"A", "B"}),
    "documented_full": tuple(spec.name for spec in _SPECS if spec.tier in {"A", "B", "C", "D", "E"}),
    "extended_full": tuple(spec.name for spec in _SPECS),
}


def parameter_names(profile: str = "documented_full") -> tuple[str, ...]:
    if profile not in PARAMETER_PROFILES:
        raise KeyError(f"unknown weight profile: {profile}")
    return PARAMETER_PROFILES[profile]


def bounds_for(profile: str = "documented_full") -> list[tuple[float, float]]:
    return [(SPECS_BY_NAME[name].minimum, SPECS_BY_NAME[name].maximum) for name in parameter_names(profile)]


def clamp_weights(weights: Mapping[str, float]) -> dict[str, float]:
    merged = dict(DEFAULTS)
    for name, value in weights.items():
        spec = SPECS_BY_NAME.get(name)
        if spec is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        merged[name] = min(spec.maximum, max(spec.minimum, numeric))
    return merged


def weights_to_vector(weights: Mapping[str, float], profile: str = "documented_full") -> list[float]:
    clamped = clamp_weights(weights)
    return [clamped[name] for name in parameter_names(profile)]


def vector_to_weights(vector: Sequence[float], profile: str = "documented_full") -> dict[str, float]:
    names = parameter_names(profile)
    if len(vector) != len(names):
        raise ValueError(f"{profile} expects {len(names)} values, got {len(vector)}")
    return clamp_weights({name: float(value) for name, value in zip(names, vector)})


def serialize_weights(weights: Mapping[str, float], *, profile: str | None = None) -> str:
    names = parameter_names(profile) if profile is not None else tuple(DEFAULTS.keys())
    clamped = clamp_weights(weights)
    payload = {name: clamped[name] for name in names}
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def save_weights(path: Path, weights: Mapping[str, float], *, profile: str | None = None) -> None:
    names = parameter_names(profile) if profile is not None else tuple(DEFAULTS.keys())
    clamped = clamp_weights(weights)
    payload = {name: clamped[name] for name in names}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_overrides_from_mapping(raw: object) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        return {}
    parsed: dict[str, float] = {}
    for name in DEFAULTS:
        if name not in raw:
            continue
        try:
            parsed[name] = float(raw[name])
        except (TypeError, ValueError):
            continue
    return parsed


def _load_json_file(path: Path) -> dict[str, float]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return _load_overrides_from_mapping(raw)


def load_weights(
    *,
    package_root: Path | None = None,
    env_var: str = "Y4_WEIGHTS_JSON",
    weights_file_name: str = "weights.json",
    allow_env: bool = True,
) -> dict[str, float]:
    """Load candidate weights with safe fallback semantics for tournament play."""

    merged = dict(DEFAULTS)

    if allow_env:
        raw_env = os.getenv(env_var)
        if raw_env:
            try:
                env_payload = json.loads(raw_env)
            except json.JSONDecodeError:
                env_payload = None
            if env_payload is not None:
                merged.update(_load_overrides_from_mapping(env_payload))
                return clamp_weights(merged)

    root = package_root if package_root is not None else Path(__file__).resolve().parent.parent
    merged.update(_load_json_file(root / weights_file_name))
    return clamp_weights(merged)


def phase_multiplier_tuple(weights: Mapping[str, float], phase: str) -> tuple[float, float, float, float, float]:
    prefix = {
        "opening": "opening",
        "mid": "mid",
        "late": "late",
    }.get(phase)
    if prefix is None:
        raise KeyError(f"unknown phase: {phase}")
    clamped = clamp_weights(weights)
    return (
        clamped[f"{prefix}_mult_a"],
        clamped[f"{prefix}_mult_b"],
        clamped[f"{prefix}_mult_c"],
        clamped[f"{prefix}_mult_d"],
        clamped[f"{prefix}_mult_f"],
    )


def select_subset(weights: Mapping[str, float], names: Iterable[str]) -> dict[str, float]:
    clamped = clamp_weights(weights)
    return {name: clamped[name] for name in names if name in clamped}
