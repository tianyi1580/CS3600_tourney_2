from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class ParameterSpec:
    """Single scalar surfaced to the offline optimizer."""

    name: str
    default: float
    minimum: float
    maximum: float
    tier: str


_SPECS: tuple[ParameterSpec, ...] = (
    # Tier A: leaf-evaluator coefficients (§6 of plan).
    # The new five-term eval is:
    #   α · score_delta + β · territory_delta + γ · chain_potential_delta
    #   + δ · mobility_delta + ε · belief_info_value − ω_threat · threat_pen
    ParameterSpec("alpha", 1.00, 0.25, 3.0, "A"),
    ParameterSpec("beta", 0.35, 0.0, 1.5, "A"),
    ParameterSpec("gamma", 0.25, 0.0, 1.5, "A"),
    ParameterSpec("delta", 0.05, 0.0, 0.6, "A"),
    ParameterSpec("epsilon", 0.12, 0.0, 0.8, "A"),
    ParameterSpec("omega_threat", 0.60, 0.0, 2.0, "A"),
    # Tier C: search-policy (rat guessing).
    ParameterSpec("lambda_denial", 0.3, 0.0, 2.0, "C"),
    ParameterSpec("search_gate_base_farm", 0.22, 0.05, 0.50, "C"),
    ParameterSpec("search_gate_slope_farm", 0.22, 0.05, 0.70, "C"),
    ParameterSpec("search_gate_base_nonfarm", 0.35, 0.10, 0.70, "C"),
    ParameterSpec("search_gate_slope_nonfarm", 0.50, 0.15, 0.95, "C"),
    ParameterSpec("info_entropy_gate", 0.75, 0.30, 0.98, "C"),
    # Tier D: time-allocation controls.
    ParameterSpec("time_opening_multiplier", 1.80, 0.5, 3.0, "D"),
    ParameterSpec("time_mid_multiplier", 1.60, 0.5, 3.0, "D"),
    ParameterSpec("time_late_multiplier", 1.20, 0.5, 2.5, "D"),
    ParameterSpec("time_complex_min", 0.70, 0.3, 1.0, "D"),
    ParameterSpec("time_complex_max", 1.60, 1.0, 2.5, "D"),
    ParameterSpec("time_reserve", 5.0, 1.0, 12.0, "D"),
    ParameterSpec("time_fraction_cap", 0.25, 0.05, 0.40, "D"),
)

SPECS_BY_NAME: dict[str, ParameterSpec] = {spec.name: spec for spec in _SPECS}
DEFAULTS: dict[str, float] = {spec.name: spec.default for spec in _SPECS}

PARAMETER_PROFILES: dict[str, tuple[str, ...]] = {
    "core": tuple(spec.name for spec in _SPECS if spec.tier in {"A", "B"}),
    "phase": tuple(spec.name for spec in _SPECS if spec.tier in {"A", "B", "C"}),
    "extended": tuple(spec.name for spec in _SPECS),
}


def parameter_names(profile: str = "extended") -> tuple[str, ...]:
    if profile not in PARAMETER_PROFILES:
        raise KeyError(f"unknown weight profile: {profile}")
    return PARAMETER_PROFILES[profile]


def bounds_for(profile: str = "extended") -> list[tuple[float, float]]:
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


def weights_to_vector(weights: Mapping[str, float], profile: str = "extended") -> list[float]:
    clamped = clamp_weights(weights)
    return [clamped[name] for name in parameter_names(profile)]


def vector_to_weights(vector: list[float] | tuple[float, ...], profile: str = "extended") -> dict[str, float]:
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
    env_var: str = "YP3_WEIGHTS_JSON",
    weights_file_name: str = "weights.json",
    allow_env: bool = True,
) -> tuple[dict[str, float], str]:
    """Load safe weight overrides for yolanda_prime_v3 and report their source."""

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
                return clamp_weights(merged), "env"

    root = package_root if package_root is not None else Path(__file__).resolve().parent.parent
    file_payload = _load_json_file(root / weights_file_name)
    if file_payload:
        merged.update(file_payload)
        return clamp_weights(merged), "package"

    return clamp_weights(merged), "default"
