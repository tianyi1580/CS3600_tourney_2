from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class ParameterSpec:
    """Single scalar exposed through the Yolanda6 weight interface."""

    name: str
    default: float
    minimum: float
    maximum: float


_SPECS: tuple[ParameterSpec, ...] = (
    ParameterSpec("a", 1.40, 0.5, 3.0),
    ParameterSpec("b", 0.45, 0.1, 1.5),
    ParameterSpec("c", 1.20, 0.3, 3.0),
    ParameterSpec("d", 0.35, 0.05, 1.5),
    ParameterSpec("f", 0.75, 0.2, 2.0),
    ParameterSpec("g", 0.50, 0.0, 1.5),
    ParameterSpec("farmable_ev_scale", 0.90, 0.5, 1.0),
    ParameterSpec("farmable_margin_base", 0.15, 0.0, 0.4),
    ParameterSpec("farmable_margin_slope", 0.20, 0.0, 0.5),
    ParameterSpec("nonfarm_margin_base", 0.25, 0.0, 0.6),
    ParameterSpec("nonfarm_margin_slope", 0.50, 0.1, 1.0),
    ParameterSpec("eval_potential_w", 0.55, 0.1, 1.5),
    ParameterSpec("eval_chain_w", 0.60, 0.1, 2.0),
    ParameterSpec("eval_exit_w", 0.35, 0.05, 1.0),
    ParameterSpec("eval_entry_adv_w", 0.30, 0.0, 1.0),
    ParameterSpec("eval_trap_w", 0.80, 0.1, 2.0),
    ParameterSpec("ownership_safe_w", 1.05, 0.1, 3.0),
    ParameterSpec("ownership_contested_w", 1.35, 0.1, 3.5),
    ParameterSpec("ownership_dead_w", 0.85, 0.0, 2.5),
    ParameterSpec("lane_steal_w", 1.20, 0.0, 3.0),
    ParameterSpec("foraging_axis_w", 0.30, 0.0, 1.5),
    ParameterSpec("search_threat_w", 1.10, 0.0, 3.0),
    ParameterSpec("lead_margin_base", 0.20, 0.0, 1.0),
    ParameterSpec("lead_margin_slope", 0.03, 0.0, 0.2),
    ParameterSpec("lead_margin_cap", 1.20, 0.0, 3.0),
    ParameterSpec("lead_prob_floor_bonus", 0.08, 0.0, 0.3),
    ParameterSpec("bb_eval_mobility_w", 0.35, 0.05, 1.5),
    ParameterSpec("bb_eval_local_chain_w", 0.45, 0.05, 2.0),
    ParameterSpec("bb_eval_trap_w", 0.55, 0.1, 2.0),
)

_SPECS_BY_NAME: dict[str, ParameterSpec] = {spec.name: spec for spec in _SPECS}
DEFAULTS: dict[str, float] = {spec.name: spec.default for spec in _SPECS}


def clamp_weights(weights: Mapping[str, float]) -> dict[str, float]:
    merged = dict(DEFAULTS)
    for name, value in weights.items():
        spec = _SPECS_BY_NAME.get(name)
        if spec is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        merged[name] = min(spec.maximum, max(spec.minimum, numeric))
    return merged


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
    env_var: str = "Y6_WEIGHTS_JSON",
    weights_file_name: str = "weights.json",
    allow_env: bool = True,
) -> tuple[dict[str, float], str]:
    """Load safe weight overrides for Yolanda6 and report their source."""

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
