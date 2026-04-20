#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATCH_ROOT = ROOT / "data" / "matches"

CORE_REQUIRED_FIELDS = (
    "turn_count",
    "result",
    "reason",
    "a_points",
    "b_points",
    "a_time_left",
    "b_time_left",
)


@dataclass(frozen=True)
class ParseIssue:
    severity: str
    field: str
    message: str


@dataclass
class NormalizedMatch:
    source_path: str
    match_id: str
    schema_version: str
    turn_count: int
    result: int
    reason: str
    timeline: dict[str, list[Any]]
    positions: dict[str, list[list[int]]]
    events: dict[str, list[Any]]
    extras: dict[str, Any]
    cohort: dict[str, str]


def _phase_ranges(length: int) -> dict[str, tuple[int, int]]:
    if length <= 0:
        return {"early": (0, 0), "mid": (0, 0), "late": (0, 0)}
    first_end = length // 3
    second_end = (2 * length) // 3
    return {
        "early": (0, first_end),
        "mid": (first_end, second_end),
        "late": (second_end, length),
    }


def _phase_for_turn(turn: int, length: int) -> str:
    for phase, (start, end) in _phase_ranges(length).items():
        if start <= turn < end:
            return phase
    return "late"


def _format_threshold_key(threshold: float) -> str:
    return f"{threshold:g}"


def _safe_fmean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _safe_median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _delta_by_turn(match: NormalizedMatch) -> list[float]:
    a_points = match.timeline["a_points"]
    b_points = match.timeline["b_points"]
    return [float(a_points[i] - b_points[i]) for i in range(min(len(a_points), len(b_points)))]


def _delta_change_by_turn(deltas: list[float]) -> list[float]:
    if not deltas:
        return []
    changes = [0.0]
    for i in range(1, len(deltas)):
        changes.append(deltas[i] - deltas[i - 1])
    return changes


def _score_delta(match: NormalizedMatch) -> float:
    return float(match.timeline["a_points"][-1] - match.timeline["b_points"][-1])


def _outcome_from_scores(match: NormalizedMatch) -> float:
    delta = _score_delta(match)
    if delta > 0:
        return 1.0
    if delta < 0:
        return 0.0
    return 0.5


def _perspective_sign(perspective: str) -> float:
    return -1.0 if perspective == "b" else 1.0


def _turn_owner(turn: int) -> str | None:
    if turn <= 0:
        return None
    return "a" if turn % 2 == 1 else "b"


def _behavior_turn_rows(match: NormalizedMatch, perspective: str) -> list[dict[str, Any]]:
    """Return behavior rows for the requested player perspective.

    Match archives store one interleaved turn stream. Perspective slicing keeps
    behavior metrics on one player's turns instead of mixing both players'
    actions into the same rate, transition, and opening-label calculations.
    """
    left = match.timeline["left_behind"]
    rat_caught = match.timeline["rat_caught"]
    deltas = _delta_by_turn(match)
    changes = _delta_change_by_turn(deltas)
    limit = min(len(left), len(rat_caught), len(deltas), len(changes))
    sign = _perspective_sign(perspective)
    rows: list[dict[str, Any]] = []
    for turn in range(limit):
        owner = _turn_owner(turn)
        if perspective in {"a", "b"} and owner != perspective:
            continue
        rows.append(
            {
                "turn": turn,
                "owner": owner,
                "mode": left[turn],
                "rat_caught": bool(rat_caught[turn]),
                "delta_after": deltas[turn],
                "delta_change": changes[turn],
                "perspective_delta_after": sign * deltas[turn],
                "perspective_delta_change": sign * changes[turn],
            }
        )
    return rows


def _safe_coord(value: Any) -> list[int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    if not all(isinstance(x, (int, float)) for x in value):
        return None
    return [int(value[0]), int(value[1])]


def _parse_left_behind(left_behind: list[Any], issues: list[ParseIssue]) -> list[str]:
    out: list[str] = []
    for i, item in enumerate(left_behind):
        if isinstance(item, str):
            out.append(item)
        else:
            issues.append(
                ParseIssue("warning", "left_behind", f"coerced non-string at index {i} to string")
            )
            out.append(str(item))
    return out


def _align_series(
    data: dict[str, Any], field: str, turn_count: int, issues: list[ParseIssue], fill_value: Any
) -> list[Any]:
    value = data.get(field)
    target_len = turn_count + 1
    if not isinstance(value, list):
        issues.append(ParseIssue("warning", field, "missing or non-list; filled with default"))
        return [fill_value] * target_len
    if len(value) == target_len:
        return value
    if len(value) == turn_count:
        issues.append(ParseIssue("warning", field, "len=turn_count; prepending inferred initial value"))
        first = value[0] if value else fill_value
        return [first] + value
    issues.append(
        ParseIssue(
            "warning",
            field,
            f"unexpected length={len(value)}; clamping/padding to {target_len}",
        )
    )
    if len(value) > target_len:
        return value[:target_len]
    if not value:
        return [fill_value] * target_len
    return value + [value[-1]] * (target_len - len(value))


def _coerce_numeric_series(
    values: list[Any], field: str, issues: list[ParseIssue], fallback: float = 0.0
) -> list[float]:
    out: list[float] = []
    for i, value in enumerate(values):
        if isinstance(value, bool):
            issues.append(ParseIssue("warning", field, f"boolean at index {i}; coerced to {fallback}"))
            out.append(float(fallback))
            continue
        if isinstance(value, (int, float)):
            out.append(float(value))
            continue
        try:
            out.append(float(value))
            issues.append(ParseIssue("warning", field, f"coerced non-numeric at index {i}"))
        except Exception:
            issues.append(ParseIssue("warning", field, f"invalid numeric at index {i}; coerced to {fallback}"))
            out.append(float(fallback))
    return out


def _coerce_bool_series(values: list[Any], field: str, issues: list[ParseIssue]) -> list[bool]:
    out: list[bool] = []
    true_tokens = {"true", "t", "1", "yes", "y"}
    false_tokens = {"false", "f", "0", "no", "n", ""}
    for i, value in enumerate(values):
        if isinstance(value, bool):
            out.append(value)
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value in (0, 1):
                issues.append(ParseIssue("warning", field, f"coerced numeric bool-like at index {i}"))
                out.append(bool(int(value)))
            else:
                issues.append(ParseIssue("warning", field, f"invalid numeric bool at index {i}; coerced to False"))
                out.append(False)
            continue
        if isinstance(value, str):
            token = value.strip().lower()
            if token in true_tokens:
                issues.append(ParseIssue("warning", field, f"coerced string bool-like at index {i}"))
                out.append(True)
                continue
            if token in false_tokens:
                issues.append(ParseIssue("warning", field, f"coerced string bool-like at index {i}"))
                out.append(False)
                continue
            issues.append(ParseIssue("warning", field, f"invalid string bool at index {i}; coerced to False"))
            out.append(False)
            continue
        issues.append(ParseIssue("warning", field, f"coerced non-bool at index {i} to False"))
        out.append(False)
    return out


def normalize_match(path: Path) -> tuple[NormalizedMatch | None, list[ParseIssue]]:
    issues: list[ParseIssue] = []
    try:
        raw = json.loads(path.read_text())
    except Exception as exc:
        return None, [ParseIssue("fatal", "json", f"invalid json: {exc}")]

    if not isinstance(raw, dict):
        return None, [ParseIssue("fatal", "json", "top-level payload must be an object")]

    missing_core = [field for field in CORE_REQUIRED_FIELDS if field not in raw]
    if missing_core:
        return None, [ParseIssue("fatal", "core_fields", f"missing required fields: {missing_core}")]

    turn_count_raw = raw.get("turn_count")
    if not isinstance(turn_count_raw, int) or turn_count_raw <= 0:
        return None, [ParseIssue("fatal", "turn_count", "turn_count must be positive int")]
    turn_count = int(turn_count_raw)

    result_raw = raw.get("result")
    if isinstance(result_raw, bool) or not isinstance(result_raw, (int, float)):
        issues.append(ParseIssue("warning", "result", "non-numeric result; coerced to 0"))
        result = 0
    else:
        result = int(result_raw)

    reason_raw = raw.get("reason")
    reason = reason_raw if isinstance(reason_raw, str) else str(reason_raw)
    if not isinstance(reason_raw, str):
        issues.append(ParseIssue("warning", "reason", "non-string reason coerced to string"))

    schema_version = "m2" if ("a_pos" in raw or "b_pos" in raw) else "yolanda"
    if schema_version == "m2":
        a_pos_src = raw.get("a_pos", [])
        b_pos_src = raw.get("b_pos", [])
    else:
        pos_src = raw.get("pos", [])
        a_pos_src = pos_src[::2] if isinstance(pos_src, list) else []
        b_pos_src = pos_src[1::2] if isinstance(pos_src, list) else []

    a_pos = [c for c in (_safe_coord(v) for v in a_pos_src) if c is not None]
    b_pos = [c for c in (_safe_coord(v) for v in b_pos_src) if c is not None]
    if len(a_pos) != len(a_pos_src):
        issues.append(ParseIssue("warning", "a_pos", "dropped malformed coordinates"))
    if len(b_pos) != len(b_pos_src):
        issues.append(ParseIssue("warning", "b_pos", "dropped malformed coordinates"))

    rat_pos_src = raw.get("rat_position_history", [])
    rat_pos = [c for c in (_safe_coord(v) for v in rat_pos_src) if c is not None]
    if rat_pos_src and len(rat_pos) != len(rat_pos_src):
        issues.append(ParseIssue("warning", "rat_position_history", "dropped malformed coordinates"))

    blocked_src = raw.get("blocked_positions", raw.get("trapdoors", []))
    blocked = [c for c in (_safe_coord(v) for v in blocked_src) if c is not None]
    if blocked_src and len(blocked) != len(blocked_src):
        issues.append(ParseIssue("warning", "blocked_or_trapdoors", "dropped malformed coordinates"))

    timeline = {
        "a_points": _coerce_numeric_series(
            _align_series(raw, "a_points", turn_count, issues, 0), "a_points", issues, fallback=0.0
        ),
        "b_points": _coerce_numeric_series(
            _align_series(raw, "b_points", turn_count, issues, 0), "b_points", issues, fallback=0.0
        ),
        "a_time_left": _coerce_numeric_series(
            _align_series(raw, "a_time_left", turn_count, issues, 0.0), "a_time_left", issues, fallback=0.0
        ),
        "b_time_left": _coerce_numeric_series(
            _align_series(raw, "b_time_left", turn_count, issues, 0.0), "b_time_left", issues, fallback=0.0
        ),
        "a_turns_left": _coerce_numeric_series(
            _align_series(raw, "a_turns_left", turn_count, issues, turn_count),
            "a_turns_left",
            issues,
            fallback=float(turn_count),
        ),
        "b_turns_left": _coerce_numeric_series(
            _align_series(raw, "b_turns_left", turn_count, issues, turn_count),
            "b_turns_left",
            issues,
            fallback=float(turn_count),
        ),
        "rat_caught": _coerce_bool_series(
            _align_series(raw, "rat_caught", turn_count, issues, False), "rat_caught", issues
        ),
        "left_behind": _parse_left_behind(_align_series(raw, "left_behind", turn_count, issues, "plain"), issues),
    }

    extras = {
        key: value
        for key, value in raw.items()
        if key
        not in {
            "a_pos",
            "b_pos",
            "pos",
            "a_points",
            "b_points",
            "a_turns_left",
            "b_turns_left",
            "a_time_left",
            "b_time_left",
            "rat_caught",
            "new_carpets",
            "left_behind",
            "rat_position_history",
            "errlog_a",
            "errlog_b",
            "turn_count",
            "result",
            "reason",
            "blocked_positions",
            "trapdoors",
            "start_time",
            "start_moves",
            "spawn_a",
            "spawn_b",
        }
    }

    match = NormalizedMatch(
        source_path=str(path),
        match_id=path.stem,
        schema_version=schema_version,
        turn_count=turn_count,
        result=result,
        reason=reason,
        timeline=timeline,
        positions={"a_pos": a_pos, "b_pos": b_pos, "rat_position_history": rat_pos},
        events={
            "blocked_or_trapdoors": blocked,
            "new_carpets": raw.get("new_carpets", []),
            "errlog_a": raw.get("errlog_a", ""),
            "errlog_b": raw.get("errlog_b", ""),
            "spawn_a": raw.get("spawn_a"),
            "spawn_b": raw.get("spawn_b"),
        },
        extras=extras,
        cohort={"source_group": path.parent.name, "schema_version": schema_version},
    )
    return match, issues


def _wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    phat = successes / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2.0 * n)) / denom
    margin = z * math.sqrt((phat * (1.0 - phat) + z * z / (4.0 * n)) / n) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def _bootstrap_mean_ci(samples: list[float], draws: int = 600, seed: int = 13) -> tuple[float, float]:
    if not samples:
        return 0.0, 0.0
    if len(samples) == 1:
        return samples[0], samples[0]
    rng = random.Random(seed)
    n = len(samples)
    means = []
    for _ in range(draws):
        draw = [samples[rng.randrange(n)] for _ in range(n)]
        means.append(statistics.fmean(draw))
    means.sort()
    lo = means[int(0.025 * (draws - 1))]
    hi = means[int(0.975 * (draws - 1))]
    return lo, hi


def _confidence_label(n: int, lo: float, hi: float, min_n: int, null_target: float = 0.0) -> str:
    if n < min_n:
        return "insufficient_data"
    if lo > null_target or hi < null_target:
        return "high_confidence"
    return "medium_confidence"


def _extract_errlog_tags(*messages: str) -> dict[str, int]:
    tags = {"timeout": 0, "crash": 0, "invalid": 0}
    pattern_map = {
        "timeout": re.compile(r"timeout", re.IGNORECASE),
        "crash": re.compile(r"crash|memory", re.IGNORECASE),
        "invalid": re.compile(r"invalid", re.IGNORECASE),
    }
    for msg in messages:
        if not isinstance(msg, str):
            continue
        for tag, pat in pattern_map.items():
            if pat.search(msg):
                tags[tag] += 1
    return tags


def _metric_row(
    matches: list[NormalizedMatch],
    cohort_name: str,
    n_min: int,
    deficit_thresholds: list[float],
    turning_point_k: int,
    top_transitions: int,
    transition_min_support: int,
    perspective: str,
) -> dict[str, Any]:
    n = len(matches)
    score_outcomes = [_outcome_from_scores(m) for m in matches]
    wins = sum(1 for v in score_outcomes if v == 1.0)
    ties = sum(1 for v in score_outcomes if v == 0.5)
    loss_equiv = n - wins - ties
    effective_wins = wins + 0.5 * ties
    win_rate = (effective_wins / n) if n else 0.0
    win_lo, win_hi = _bootstrap_mean_ci(score_outcomes)

    deltas = []
    search_turns = 0
    search_catches = 0
    left_behind_counts: dict[str, int] = {}
    timeout_pressure = 0
    err_tags = {"timeout": 0, "crash": 0, "invalid": 0}
    catastrophic_losses = 0
    drawdowns: list[float] = []
    drawdown_spans: list[float] = []
    deficit_payload: dict[str, dict[str, list[float]]] = {
        _format_threshold_key(t): {
            "time_turns": [],
            "time_fraction": [],
            "crossed": [],
            "recovered_after_cross": [],
            "recovery_latency": [],
        }
        for t in deficit_thresholds
    }

    for match in matches:
        delta = _score_delta(match)
        deltas.append(delta)
        for row in _behavior_turn_rows(match, perspective):
            mode = str(row["mode"])
            left_behind_counts[mode] = left_behind_counts.get(mode, 0) + 1
            if mode == "search":
                search_turns += 1
                if bool(row["rat_caught"]):
                    search_catches += 1
        if min(match.timeline["a_time_left"][-1], match.timeline["b_time_left"][-1]) < 5.0:
            timeout_pressure += 1
        tags = _extract_errlog_tags(match.events.get("errlog_a", ""), match.events.get("errlog_b", ""))
        for key, val in tags.items():
            err_tags[key] += val
        # Catastrophic loss is a severe points blowout, not a crash.
        if delta <= -15.0:
            catastrophic_losses += 1
        deltas_by_turn = _delta_by_turn(match)
        dd = _max_drawdown(deltas_by_turn)
        drawdowns.append(dd["max_drawdown"])
        drawdown_spans.append(dd["span_turns"])
        for threshold in deficit_thresholds:
            key = _format_threshold_key(threshold)
            tid = _time_in_deficit_stats(deltas_by_turn, threshold)
            rec = _recovery_after_first_crossing(deltas_by_turn, threshold)
            deficit_payload[key]["time_turns"].append(tid["turns"])
            deficit_payload[key]["time_fraction"].append(tid["fraction"])
            deficit_payload[key]["crossed"].append(rec["crossed"])
            deficit_payload[key]["recovered_after_cross"].append(rec["recovered"])
            if rec["crossed"] > 0:
                deficit_payload[key]["recovery_latency"].append(rec["recovery_latency_turns"])

    mean_delta = statistics.fmean(deltas) if deltas else 0.0
    d_lo, d_hi = _bootstrap_mean_ci(deltas)

    search_rate = (search_catches / search_turns) if search_turns else 0.0
    s_lo, s_hi = _wilson_interval(search_catches, search_turns)
    timeout_rate = (timeout_pressure / n) if n else 0.0
    catastrophic_rate = (catastrophic_losses / n) if n else 0.0

    top_modes = sorted(left_behind_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
    loss_driver_summary = _loss_drivers(matches, perspective=perspective)
    phase_split = _compute_phase_split(matches, perspective=perspective)
    transition_patterns = _compute_transition_patterns(
        matches,
        top_n=top_transitions,
        min_support=max(1, int(transition_min_support)),
        perspective=perspective,
    )
    deficit_onset = _compute_deficit_onset(matches, thresholds=deficit_thresholds)
    turning_points = _turning_points_summary(matches, k=turning_point_k, perspective=perspective)
    recommendations: list[str] = []
    if n >= n_min and d_hi < 0:
        recommendations.append(
            "Negative score delta is persistent; prioritize policy weight retuning and deeper lookahead checks."
        )
    if search_turns >= n_min and s_hi < 0.35:
        recommendations.append(
            "Search conversion is low; tune search trigger thresholds and belief/adaptation parameters."
        )
    if n >= n_min and timeout_rate > 0.2:
        recommendations.append("Timeout pressure is elevated; tighten time budget caps and reduce expensive branches.")
    if n >= n_min and catastrophic_rate > 0.15:
        recommendations.append("Catastrophic loss rate is high; add guardrail heuristics for losing states.")
    if loss_driver_summary:
        for line in loss_driver_summary["recommendations"]:
            recommendations.append(line)
    if (
        phase_split["losses"]["early"]["mean_delta_change"] < -2.0
        and phase_split["wins"]["early"]["mean_delta_change"] > phase_split["losses"]["early"]["mean_delta_change"]
    ):
        recommendations.append(
            f"Early phase collapses in losses (mean delta change {phase_split['losses']['early']['mean_delta_change']:+.2f}); tighten opening move safety and reduce high-variance branches in first third."
        )
    top_gap = transition_patterns["top_gaps"][0] if transition_patterns["top_gaps"] else None
    if top_gap and top_gap["direction"] == "loss_heavier" and top_gap["gap_abs"] > 0.03:
        recommendations.append(
            f"Transition `{top_gap['transition']}` is loss-heavier (gap {top_gap['gap_abs']:.3f}); revisit policy thresholds governing this move switch."
        )
    d10_key = _format_threshold_key(-10.0)
    if d10_key in deficit_onset:
        losses_d10 = deficit_onset[d10_key]["losses"]
        if losses_d10["onset_rate"] > 0.5 and losses_d10["median_turn"] <= 20:
            recommendations.append(
                f"Deficit onset below -10 happens early in losses (rate {losses_d10['onset_rate']:.2f}, median turn {losses_d10['median_turn']:.1f}); increase early recovery bias and defensive search discipline."
            )

    trajectory_robustness = {
        "max_drawdown": {
            "mean": _safe_fmean(drawdowns),
            "median": _safe_median(drawdowns),
            "ci95": list(_bootstrap_mean_ci(drawdowns)),
        },
        "drawdown_span_turns": {
            "mean": _safe_fmean(drawdown_spans),
            "median": _safe_median(drawdown_spans),
            "ci95": list(_bootstrap_mean_ci(drawdown_spans)),
        },
        "thresholds": {},
    }
    for key, payload in deficit_payload.items():
        crossed_total = int(sum(payload["crossed"]))
        recovered_total = int(sum(payload["recovered_after_cross"]))
        trajectory_robustness["thresholds"][key] = {
            "mean_time_in_deficit_turns": _safe_fmean(payload["time_turns"]),
            "median_time_in_deficit_turns": _safe_median(payload["time_turns"]),
            "mean_time_in_deficit_fraction": _safe_fmean(payload["time_fraction"]),
            "cross_rate": (crossed_total / n) if n else 0.0,
            "recovery_rate_after_cross": (recovered_total / crossed_total) if crossed_total else 0.0,
            "mean_recovery_latency_turns": _safe_fmean(payload["recovery_latency"]),
            "recovery_latency_ci95": list(_bootstrap_mean_ci(payload["recovery_latency"])),
        }

    return {
        "cohort": cohort_name,
        "sample_size": n,
        "outcome": {
            "win_rate": win_rate,
            "win_rate_ci95": [win_lo, win_hi],
            "win_confidence": _confidence_label(n, win_lo, win_hi, n_min, null_target=0.5),
            "wins": wins,
            "losses": loss_equiv,
            "ties": ties,
            "mean_score_delta": mean_delta,
            "mean_score_delta_ci95": [d_lo, d_hi],
            "delta_confidence": _confidence_label(n, d_lo, d_hi, n_min, null_target=0.0),
            "reason_distribution": _distribution([m.reason for m in matches]),
        },
        "behavior": {
            "search_conversion_rate": search_rate,
            "search_conversion_ci95": [s_lo, s_hi],
            "search_confidence": _confidence_label(
                search_turns,
                s_lo,
                s_hi,
                n_min,
                null_target=0.25,
            ),
            "left_behind_top_modes": top_modes,
        },
        "reliability": {
            "timeout_pressure_rate": timeout_rate,
            "catastrophic_loss_rate": catastrophic_rate,
            "catastrophic_loss_definition": "final score delta <= -15 points",
            "errlog_tag_counts": err_tags,
        },
        "phase_split": phase_split,
        "transition_patterns": transition_patterns,
        "deficit_onset": deficit_onset,
        "trajectory_robustness": trajectory_robustness,
        "turning_points_summary": turning_points,
        "loss_drivers": loss_driver_summary["metrics"] if loss_driver_summary else {},
        "actions": recommendations,
    }


def _distribution(values: list[str]) -> dict[str, float]:
    total = len(values)
    if total == 0:
        return {}
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return {key: val / total for key, val in sorted(counts.items())}


def _compute_phase_split(matches: list[NormalizedMatch], perspective: str = "all") -> dict[str, Any]:
    bucketed: dict[str, list[NormalizedMatch]] = {
        "wins": [m for m in matches if _score_delta(m) > 0],
        "losses": [m for m in matches if _score_delta(m) < 0],
        "ties": [m for m in matches if _score_delta(m) == 0],
    }
    out: dict[str, Any] = {}
    for label, bucket in bucketed.items():
        phase_rows: dict[str, Any] = {}
        for phase in ("early", "mid", "late"):
            end_deltas = []
            delta_changes = []
            mode_counts: dict[str, int] = {}
            search_turns = 0
            search_catches = 0
            for match in bucket:
                deltas = _delta_by_turn(match)
                changes = _delta_change_by_turn(deltas)
                start, end = _phase_ranges(len(deltas))[phase]
                if start >= end or end > len(deltas):
                    continue
                end_deltas.append(deltas[end - 1])
                delta_changes.append(sum(changes[start:end]))
                phase_rows_for_match = [
                    row
                    for row in _behavior_turn_rows(match, perspective)
                    if start <= int(row["turn"]) < end
                ]
                for row in phase_rows_for_match:
                    mode = str(row["mode"])
                    mode_counts[mode] = mode_counts.get(mode, 0) + 1
                    if mode == "search":
                        search_turns += 1
                        if bool(row["rat_caught"]):
                            search_catches += 1
            phase_rows[phase] = {
                "mean_phase_end_delta": statistics.fmean(end_deltas) if end_deltas else 0.0,
                "mean_delta_change": statistics.fmean(delta_changes) if delta_changes else 0.0,
                "search_conversion": (search_catches / search_turns) if search_turns else 0.0,
                "mode_mix": _distribution(
                    [k for k, v in mode_counts.items() for _ in range(v)]
                ),
            }
        out[label] = phase_rows
    return out


def _compute_transition_patterns(
    matches: list[NormalizedMatch],
    top_n: int,
    min_support: int = 1,
    *,
    perspective: str = "all",
) -> dict[str, Any]:
    buckets = {
        "wins": [m for m in matches if _score_delta(m) > 0],
        "losses": [m for m in matches if _score_delta(m) < 0],
    }
    pair_counts: dict[str, dict[str, int]] = {"wins": {}, "losses": {}}
    totals: dict[str, int] = {"wins": 0, "losses": 0}
    for label, bucket in buckets.items():
        for match in bucket:
            seq = [str(row["mode"]) for row in _behavior_turn_rows(match, perspective)]
            for i in range(len(seq) - 1):
                key = f"{seq[i]}->{seq[i + 1]}"
                pair_counts[label][key] = pair_counts[label].get(key, 0) + 1
                totals[label] += 1
    all_keys = set(pair_counts["wins"]) | set(pair_counts["losses"])
    rows = []
    dropped_low_support = 0
    for key in all_keys:
        w = pair_counts["wins"].get(key, 0)
        l = pair_counts["losses"].get(key, 0)
        support = w + l
        if support < min_support:
            dropped_low_support += 1
            continue
        w_rate = w / totals["wins"] if totals["wins"] else 0.0
        l_rate = l / totals["losses"] if totals["losses"] else 0.0
        rows.append(
            {
                "transition": key,
                "support": support,
                "win_rate": w_rate,
                "loss_rate": l_rate,
                "gap_abs": abs(w_rate - l_rate),
                "direction": "loss_heavier" if l_rate > w_rate else "win_heavier",
            }
        )
    rows.sort(key=lambda item: item["gap_abs"], reverse=True)
    return {
        "top_gaps": rows[:top_n],
        "totals": totals,
        "normalization": "turn_weighted",
        "min_support": min_support,
        "dropped_low_support": dropped_low_support,
    }


def _time_in_deficit_stats(deltas: list[float], threshold: float) -> dict[str, float]:
    if not deltas:
        return {"turns": 0.0, "fraction": 0.0}
    turns = sum(1 for delta in deltas if delta <= threshold)
    return {"turns": float(turns), "fraction": turns / len(deltas)}


def _max_drawdown(deltas: list[float]) -> dict[str, float]:
    if not deltas:
        return {"max_drawdown": 0.0, "peak_turn": 0.0, "trough_turn": 0.0, "span_turns": 0.0}
    peak = deltas[0]
    peak_turn = 0
    best_drawdown = 0.0
    trough_turn = 0
    drawdown_peak_turn = 0
    for i, delta in enumerate(deltas):
        if delta > peak:
            peak = delta
            peak_turn = i
        drawdown = peak - delta
        if drawdown > best_drawdown:
            best_drawdown = drawdown
            trough_turn = i
            drawdown_peak_turn = peak_turn
    return {
        "max_drawdown": float(best_drawdown),
        "peak_turn": float(drawdown_peak_turn),
        "trough_turn": float(trough_turn),
        "span_turns": float(max(0, trough_turn - drawdown_peak_turn)),
    }


def _recovery_after_first_crossing(deltas: list[float], threshold: float) -> dict[str, float]:
    onset = _first_onset_turn(deltas, threshold)
    if onset is None:
        return {
            "crossed": 0.0,
            "crossing_turn": 0.0,
            "recovered": 0.0,
            "recovery_latency_turns": 0.0,
        }
    for turn in range(onset + 1, len(deltas)):
        if deltas[turn] > threshold:
            return {
                "crossed": 1.0,
                "crossing_turn": float(onset),
                "recovered": 1.0,
                "recovery_latency_turns": float(turn - onset),
            }
    return {
        "crossed": 1.0,
        "crossing_turn": float(onset),
        "recovered": 0.0,
        "recovery_latency_turns": float(len(deltas) - 1 - onset),
    }


def _behavior_vector_for_match(match: NormalizedMatch, opening_horizon: int, perspective: str) -> dict[str, float]:
    rows = _behavior_turn_rows(match, perspective)
    h = max(1, min(opening_horizon, len(rows)))
    early = rows[:h]
    changes = [str(row["mode"]) for row in early]
    perspective_changes = [float(row["perspective_delta_change"]) for row in early]
    return {
        "search_rate": (sum(1 for item in changes if item == "search") / h),
        "prime_rate": (sum(1 for item in changes if item == "prime") / h),
        "carpet_rate": (sum(1 for item in changes if item == "carpet") / h),
        "plain_rate": (sum(1 for item in changes if item == "plain") / h),
        "delta_slope": _safe_fmean(perspective_changes),
        "delta_volatility": statistics.pstdev(perspective_changes) if len(perspective_changes) > 1 else 0.0,
        "search_conversion": _avg_search_conversion([match], perspective=perspective),
    }


def _derive_opponent_archetype(match: NormalizedMatch, opening_horizon: int, perspective: str) -> str:
    vec = _behavior_vector_for_match(match, opening_horizon, perspective)
    if vec["search_rate"] >= 0.35:
        return "search_heavy"
    if vec["prime_rate"] >= 0.5:
        return "prime_heavy"
    if vec["delta_volatility"] >= 3.0:
        return "high_variance"
    if vec["plain_rate"] >= 0.45:
        return "slow_burn"
    return "balanced"


def _derive_map_seed(match: NormalizedMatch) -> str:
    for key in ("map_seed", "seed"):
        if key in match.extras and match.extras[key] is not None:
            return str(match.extras[key])
    static_payload = {
        "blocked_or_trapdoors": sorted(match.events.get("blocked_or_trapdoors", [])),
        "spawn_a": match.events.get("spawn_a"),
        "spawn_b": match.events.get("spawn_b"),
    }
    fingerprint = hashlib.sha1(json.dumps(static_payload, sort_keys=True).encode("utf-8")).hexdigest()[:8]
    return f"map:{fingerprint}"


def _derive_opening_fields(match: NormalizedMatch, opening_horizon: int, perspective: str) -> tuple[str, str]:
    rows = _behavior_turn_rows(match, perspective)
    h = max(1, min(opening_horizon, len(rows)))
    tokens = []
    for i in range(h):
        mode = str(rows[i]["mode"])
        delta_after = float(rows[i]["perspective_delta_after"])
        delta_bin = "up" if delta_after > 0 else "down" if delta_after < 0 else "flat"
        tokens.append(f"{mode}:{delta_bin}")
    signature_src = "|".join(tokens)
    opening_signature = hashlib.sha1(signature_src.encode("utf-8")).hexdigest()[:10]
    opening_modes = [str(row["mode"]) for row in rows[:h]]
    search_first = sum(1 for item in opening_modes if item == "search")
    prime_first = sum(1 for item in opening_modes if item == "prime")
    if search_first >= max(2, h // 3):
        family = "search_first"
    elif prime_first >= max(2, h // 3):
        family = "prime_chain"
    else:
        family = "balanced_opening"
    return family, opening_signature


def _with_derived_cohort_fields(
    matches: list[NormalizedMatch],
    opening_horizon: int,
    perspective: str,
) -> list[NormalizedMatch]:
    enriched: list[NormalizedMatch] = []
    for match in matches:
        opening_family, opening_signature = _derive_opening_fields(match, opening_horizon, perspective)
        match.cohort["opponent_archetype"] = _derive_opponent_archetype(match, opening_horizon, perspective)
        match.cohort["map_seed"] = _derive_map_seed(match)
        match.cohort["opening_family"] = opening_family
        match.cohort["opening_signature"] = opening_signature
        match.cohort["cohort_schema_version"] = "1"
        enriched.append(match)
    return enriched


def _build_stratified_cohorts(
    matches: list[NormalizedMatch], stratify_by: list[str], max_cohorts: int, rare_min_support: int
) -> list[tuple[str, list[NormalizedMatch], dict[str, str]]]:
    buckets: dict[tuple[str, ...], list[NormalizedMatch]] = {}
    for match in matches:
        key = tuple(str(match.cohort.get(field, "unknown")) for field in stratify_by)
        buckets.setdefault(key, []).append(match)
    collapsed: dict[tuple[str, ...], list[NormalizedMatch]] = {}
    for key, rows in buckets.items():
        mapped = tuple("other" if len(rows) < rare_min_support else part for part in key)
        collapsed.setdefault(mapped, []).extend(rows)
    ordered = sorted(collapsed.items(), key=lambda item: len(item[1]), reverse=True)[:max_cohorts]
    out: list[tuple[str, list[NormalizedMatch], dict[str, str]]] = []
    for key, rows in ordered:
        fields = {stratify_by[i]: key[i] for i in range(len(key))}
        label = "segment:" + ",".join(f"{k}={v}" for k, v in fields.items())
        out.append((label, rows, fields))
    return out


def _first_onset_turn(deltas: list[float], threshold: float) -> int | None:
    for i, delta in enumerate(deltas):
        if delta <= threshold:
            return i
    return None


def _quantile(sorted_values: list[int], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (len(sorted_values) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_values[lo])
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def _compute_deficit_onset(matches: list[NormalizedMatch], thresholds: list[float]) -> dict[str, Any]:
    by_outcome = {
        "wins": [m for m in matches if _score_delta(m) > 0],
        "losses": [m for m in matches if _score_delta(m) < 0],
        "ties": [m for m in matches if _score_delta(m) == 0],
    }
    result: dict[str, Any] = {}
    for threshold in thresholds:
        key = _format_threshold_key(threshold)
        result[key] = {}
        for label, bucket in by_outcome.items():
            onset_turns = []
            for match in bucket:
                onset = _first_onset_turn(_delta_by_turn(match), threshold)
                if onset is not None:
                    onset_turns.append(onset)
            onset_turns.sort()
            result[key][label] = {
                "onset_rate": (len(onset_turns) / len(bucket)) if bucket else 0.0,
                "median_turn": _quantile(onset_turns, 0.5),
                "q1_turn": _quantile(onset_turns, 0.25),
                "q3_turn": _quantile(onset_turns, 0.75),
                "sample_crossed": len(onset_turns),
                "sample_total": len(bucket),
            }
    return result


def _top_turning_points(
    match: NormalizedMatch,
    k: int,
    *,
    perspective: str = "all",
    view: str = "all",
) -> list[dict[str, Any]]:
    deltas = _delta_by_turn(match)
    changes = _delta_change_by_turn(deltas)
    points = []
    perspective_sign = _perspective_sign(perspective)
    for turn in range(1, len(changes)):
        owner = _turn_owner(turn)
        if perspective != "all":
            if view == "self_inflicted" and owner != perspective:
                continue
            if view == "opponent_swing" and owner == perspective:
                continue
        points.append(
            {
                "turn": turn,
                "turn_owner": owner,
                "delta_before": deltas[turn - 1],
                "delta_after": deltas[turn],
                "delta_change": changes[turn],
                "perspective_delta_change": perspective_sign * changes[turn],
                "left_behind_turn": match.timeline["left_behind"][turn]
                if turn < len(match.timeline["left_behind"])
                else "unknown",
                "rat_caught_turn": bool(match.timeline["rat_caught"][turn])
                if turn < len(match.timeline["rat_caught"])
                else False,
                "phase": _phase_for_turn(turn, len(deltas)),
            }
        )
    sort_key = "delta_change" if perspective == "all" else "perspective_delta_change"
    points.sort(key=lambda row: row[sort_key])
    return points[:k]


def _turning_points_summary(matches: list[NormalizedMatch], k: int, perspective: str = "all") -> dict[str, Any]:
    if perspective == "all":
        per_file = []
        phase_counts = {"early": 0, "mid": 0, "late": 0}
        for match in matches:
            top_points = _top_turning_points(match, k, perspective=perspective, view="all")
            for row in top_points:
                phase = row["phase"]
                if phase in phase_counts:
                    phase_counts[phase] += 1
            per_file.append({"match_id": match.match_id, "source_path": match.source_path, "top_turns": top_points})
        return {"per_file": per_file, "phase_counts": phase_counts}

    summary: dict[str, Any] = {}
    for view in ("self_inflicted", "opponent_swing"):
        per_file = []
        phase_counts = {"early": 0, "mid": 0, "late": 0}
        for match in matches:
            top_points = _top_turning_points(match, k, perspective=perspective, view=view)
            for row in top_points:
                phase = row["phase"]
                if phase in phase_counts:
                    phase_counts[phase] += 1
            per_file.append({"match_id": match.match_id, "source_path": match.source_path, "top_turns": top_points})
        summary[view] = {"per_file": per_file, "phase_counts": phase_counts}
    return summary


def _avg_mode_rate(matches: list[NormalizedMatch], mode: str, perspective: str) -> float:
    if not matches:
        return 0.0
    rates = []
    for match in matches:
        seq = [str(row["mode"]) for row in _behavior_turn_rows(match, perspective)]
        rates.append((sum(1 for item in seq if item == mode) / len(seq)) if seq else 0.0)
    return statistics.fmean(rates) if rates else 0.0


def _avg_search_conversion(matches: list[NormalizedMatch], perspective: str) -> float:
    searches = catches = 0
    for match in matches:
        for row in _behavior_turn_rows(match, perspective):
            mode = str(row["mode"])
            if mode != "search":
                continue
            searches += 1
            if bool(row["rat_caught"]):
                catches += 1
    return (catches / searches) if searches else 0.0


def _loss_drivers(matches: list[NormalizedMatch], perspective: str) -> dict[str, Any] | None:
    losses = [m for m in matches if _score_delta(m) < 0]
    wins = [m for m in matches if _score_delta(m) > 0]
    if not losses:
        return None

    loss_prime = _avg_mode_rate(losses, "prime", perspective)
    win_prime = _avg_mode_rate(wins, "prime", perspective) if wins else 0.0
    loss_search_conv = _avg_search_conversion(losses, perspective)
    win_search_conv = _avg_search_conversion(wins, perspective) if wins else 0.0

    recommendations: list[str] = []
    if loss_prime - win_prime > 0.08:
        recommendations.append(
            "Losses over-index on PRIME turns; reduce over-priming in trailing states and shift budget to SEARCH/CARPET opportunities."
        )
    if win_search_conv - loss_search_conv > 0.08:
        recommendations.append(
            "Search conversion is materially worse in losses; tighten belief threshold for SEARCH and raise fallback value floor before committing."
        )

    metrics = {
        "loss_count": len(losses),
        "win_count": len(wins),
        "mean_delta_losses": statistics.fmean([_score_delta(m) for m in losses]),
        "mean_delta_wins": statistics.fmean([_score_delta(m) for m in wins]) if wins else 0.0,
        "prime_rate_losses": loss_prime,
        "prime_rate_wins": win_prime,
        "search_conversion_losses": loss_search_conv,
        "search_conversion_wins": win_search_conv,
    }
    return {"metrics": metrics, "recommendations": recommendations}


def _bootstrap_delta_ci(loss_samples: list[float], win_samples: list[float], draws: int = 600, seed: int = 17) -> tuple[float, float]:
    if not loss_samples or not win_samples:
        return 0.0, 0.0
    rng = random.Random(seed)
    l_n = len(loss_samples)
    w_n = len(win_samples)
    deltas = []
    for _ in range(draws):
        l_draw = [loss_samples[rng.randrange(l_n)] for _ in range(l_n)]
        w_draw = [win_samples[rng.randrange(w_n)] for _ in range(w_n)]
        deltas.append(statistics.fmean(w_draw) - statistics.fmean(l_draw))
    deltas.sort()
    lo = deltas[int(0.025 * (draws - 1))]
    hi = deltas[int(0.975 * (draws - 1))]
    return lo, hi


def _behavior_contrasts(matches: list[NormalizedMatch], n_min: int, perspective: str) -> dict[str, Any]:
    wins = [m for m in matches if _score_delta(m) > 0]
    losses = [m for m in matches if _score_delta(m) < 0]
    if not wins or not losses:
        return {"metrics": {}, "actions": []}

    def mode_rate(match: NormalizedMatch, mode: str) -> float:
        seq = [str(row["mode"]) for row in _behavior_turn_rows(match, perspective)]
        return (sum(1 for item in seq if item == mode) / len(seq)) if seq else 0.0

    rows: dict[str, Any] = {}
    actions: list[str] = []
    contrasts = {
        "search_conversion_delta": (
            [_avg_search_conversion([m], perspective) for m in losses],
            [_avg_search_conversion([m], perspective) for m in wins],
        ),
        "prime_rate_delta": ([mode_rate(m, "prime") for m in losses], [mode_rate(m, "prime") for m in wins]),
        "search_rate_delta": ([mode_rate(m, "search") for m in losses], [mode_rate(m, "search") for m in wins]),
        "carpet_rate_delta": ([mode_rate(m, "carpet") for m in losses], [mode_rate(m, "carpet") for m in wins]),
        "plain_rate_delta": ([mode_rate(m, "plain") for m in losses], [mode_rate(m, "plain") for m in wins]),
    }
    for name, (loss_samples, win_samples) in contrasts.items():
        delta = _safe_fmean(win_samples) - _safe_fmean(loss_samples)
        lo, hi = _bootstrap_delta_ci(loss_samples, win_samples)
        confidence = _confidence_label(min(len(wins), len(losses)), lo, hi, n_min, null_target=0.0)
        rows[name] = {
            "delta": delta,
            "ci95": [lo, hi],
            "wins_n": len(win_samples),
            "losses_n": len(loss_samples),
            "confidence": confidence,
        }
        if name == "search_conversion_delta" and confidence == "high_confidence" and hi < 0:
            actions.append("Search conversion is materially weaker in wins-vs-loss contrast; inspect search gating and fallback valuation.")
    return {"metrics": rows, "actions": actions}


def build_insights(
    matches: list[NormalizedMatch],
    n_min: int,
    deficit_thresholds: list[float] | None = None,
    turning_point_k: int = 3,
    top_transitions: int = 8,
    transition_min_support: int = 5,
    stratify_by: list[str] | None = None,
    opening_horizon: int = 8,
    max_cohorts: int = 8,
    rare_min_support: int = 3,
    cohort_name: str = "all",
    perspective: str = "all",
) -> dict[str, Any]:
    if deficit_thresholds is None:
        deficit_thresholds = [-5.0, -10.0, -15.0]
    if stratify_by is None:
        stratify_by = ["opponent_archetype", "map_seed", "opening_family"]
    matches = _with_derived_cohort_fields(
        matches,
        opening_horizon=opening_horizon,
        perspective=perspective,
    )
    cohorts = []
    global_row = _metric_row(
        matches,
        cohort_name,
        n_min=n_min,
        deficit_thresholds=deficit_thresholds,
        turning_point_k=turning_point_k,
        top_transitions=top_transitions,
        transition_min_support=transition_min_support,
        perspective=perspective,
    )
    contrasts = _behavior_contrasts(matches, n_min=n_min, perspective=perspective)
    global_row["behavior_contrasts"] = contrasts["metrics"]
    global_row["actions"].extend(contrasts["actions"])
    global_row["cohort_type"] = "global"
    global_row["cohort_dimensions"] = {}
    cohorts.append(global_row)

    for label, rows, dimensions in _build_stratified_cohorts(
        matches, stratify_by=stratify_by, max_cohorts=max_cohorts, rare_min_support=rare_min_support
    ):
        row = _metric_row(
            rows,
            label,
            n_min=n_min,
            deficit_thresholds=deficit_thresholds,
            turning_point_k=turning_point_k,
            top_transitions=top_transitions,
            transition_min_support=transition_min_support,
            perspective=perspective,
        )
        contrasts = _behavior_contrasts(rows, n_min=n_min, perspective=perspective)
        row["behavior_contrasts"] = contrasts["metrics"]
        row["actions"].extend(contrasts["actions"])
        row["cohort_type"] = "segment"
        row["cohort_dimensions"] = dimensions
        cohorts.append(row)

    global_actions = list(cohorts[0]["actions"]) if cohorts else []
    return {
        "version": 2,
        "match_count": len(matches),
        "perspective": perspective,
        "n_min": n_min,
        "deficit_thresholds": deficit_thresholds,
        "turning_point_k": turning_point_k,
        "top_transitions": top_transitions,
        "transition_min_support": transition_min_support,
        "stratify_by": stratify_by,
        "opening_horizon": opening_horizon,
        "max_cohorts": max_cohorts,
        "rare_min_support": rare_min_support,
        "cohorts": cohorts,
        "global_actions": global_actions,
    }


def render_markdown(insights: dict[str, Any]) -> str:
    lines = []
    cohorts = insights.get("cohorts", [])
    global_cohorts = [cohort for cohort in cohorts if cohort.get("cohort_type", "global") == "global"]
    segment_cohorts = [cohort for cohort in cohorts if cohort.get("cohort_type") == "segment"]
    display_global = global_cohorts[0] if global_cohorts else (cohorts[0] if cohorts else None)
    primary_cohort = insights["cohorts"][0]["cohort"] if insights.get("cohorts") else "selected cohort"
    perspective = insights.get("perspective", "all")

    def _append_cohort_details(cohort: dict[str, Any]) -> None:
        outcome = cohort["outcome"]
        behavior = cohort["behavior"]
        reliability = cohort["reliability"]
        lines.append(f"### {cohort['cohort']}")
        lines.append("")
        lines.append("#### Data")
        lines.append("| Metric | Value | Confidence |")
        lines.append("|---|---|---|")
        lines.append(
            f"| Win rate | {outcome['win_rate']:.3f} (CI95 [{outcome['win_rate_ci95'][0]:.3f}, {outcome['win_rate_ci95'][1]:.3f}]) | {outcome['win_confidence']} |"
        )
        lines.append(f"| W/L/T | {outcome['wins']}/{outcome['losses']}/{outcome['ties']} | - |")
        lines.append(
            f"| Mean score delta | {outcome['mean_score_delta']:+.2f} (CI95 [{outcome['mean_score_delta_ci95'][0]:+.2f}, {outcome['mean_score_delta_ci95'][1]:+.2f}]) | {outcome['delta_confidence']} |"
        )
        lines.append(
            f"| Search conversion | {behavior['search_conversion_rate']:.3f} (CI95 [{behavior['search_conversion_ci95'][0]:.3f}, {behavior['search_conversion_ci95'][1]:.3f}]) | {behavior['search_confidence']} |"
        )
        lines.append(f"| Timeout pressure | {reliability['timeout_pressure_rate']:.3f} | - |")
        lines.append(
            f"| Catastrophic loss | {reliability['catastrophic_loss_rate']:.3f} (`{reliability['catastrophic_loss_definition']}`) | - |"
        )
        lines.append("")
        lines.append("#### Definitions")
        lines.append("- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.")
        lines.append("- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.")
        if perspective == "all":
            lines.append("- `Search conversion`: rat catches divided by search turns.")
        else:
            lines.append("- `Search conversion`: rat catches divided by search turns for the selected perspective only.")
        lines.append("- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.")
        lines.append("- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.")
        lines.append("")
        lines.append("#### Interpretation")
        if outcome["delta_confidence"] == "high_confidence" and outcome["mean_score_delta_ci95"][1] < 0:
            lines.append("- Persistent underperformance signal: CI95 for mean score delta remains below zero.")
        elif outcome["delta_confidence"] == "high_confidence" and outcome["mean_score_delta_ci95"][0] > 0:
            lines.append("- Persistent outperformance signal: CI95 for mean score delta remains above zero.")
        else:
            lines.append("- Outcome direction is less stable; gather more matches before strong conclusions.")
        if behavior["search_conversion_ci95"][1] < 0.35:
            lines.append("- Search conversion appears weak; inspect search trigger quality and fallback policy.")
        if reliability["catastrophic_loss_rate"] > 0.15:
            lines.append("- Elevated catastrophic loss risk; prioritize guardrails in losing trajectories.")
        lines.append("")
        drivers = cohort.get("loss_drivers", {})
        if drivers:
            lines.append("#### Loss Drivers")
            lines.append(
                f"- PRIME rate (loss/win): {drivers.get('prime_rate_losses', 0.0):.3f} / {drivers.get('prime_rate_wins', 0.0):.3f}"
            )
            lines.append(
                f"- Search conversion (loss/win): {drivers.get('search_conversion_losses', 0.0):.3f} / {drivers.get('search_conversion_wins', 0.0):.3f}"
            )
            lines.append("")
        if cohort["actions"]:
            lines.append("#### Recommended Actions")
            for i, action in enumerate(cohort["actions"], start=1):
                lines.append(f"{i}. {action}")
            lines.append("")
        else:
            lines.append("#### Recommended Actions")
            lines.append("- None")
            lines.append("")
        phase_split = cohort.get("phase_split", {})
        if phase_split:
            lines.append("#### Diagnostics: Phase Split (mean delta change)")
            lines.append("")
            lines.append("- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).")
            lines.append("- Sign: positive means A gains relative points in that phase; negative means A loses relative points.")
            lines.append("- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.")
            lines.append("")
            lines.append("| Phase | Wins | Losses | Ties |")
            lines.append("|---|---:|---:|---:|")
            for phase in ("early", "mid", "late"):
                win_v = phase_split.get("wins", {}).get(phase, {}).get("mean_delta_change", 0.0)
                loss_v = phase_split.get("losses", {}).get(phase, {}).get("mean_delta_change", 0.0)
                tie_v = phase_split.get("ties", {}).get(phase, {}).get("mean_delta_change", 0.0)
                lines.append(f"| {phase} | {win_v:+.2f} | {loss_v:+.2f} | {tie_v:+.2f} |")
            lines.append("")
        transition_patterns = cohort.get("transition_patterns", {}).get("top_gaps", [])
        if transition_patterns:
            lines.append("#### Diagnostics: Transition Patterns (largest win/loss gaps)")
            lines.append("")
            lines.append("- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.")
            lines.append("- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.")
            lines.append("- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.")
            lines.append(
                f"- Only transitions with support >= {cohort.get('transition_patterns', {}).get('min_support', 1)} are shown."
            )
            lines.append("- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.")
            lines.append("")
            lines.append("| Transition | Support | Win rate | Loss rate | Gap | Bias |")
            lines.append("|---|---:|---:|---:|---:|---|")
            for row in transition_patterns[:5]:
                lines.append(
                    f"| `{row['transition']}` | {row.get('support', 0)} | {row['win_rate']:.3f} | {row['loss_rate']:.3f} | {row['gap_abs']:.3f} | {row['direction']} |"
                )
            lines.append("")
        deficit_onset = cohort.get("deficit_onset", {})
        if deficit_onset:
            lines.append("#### Diagnostics: Deficit Onset (losses)")
            lines.append("")
            lines.append("- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.")
            lines.append("- `Onset rate` = fraction of loss matches that ever cross that threshold.")
            lines.append("- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.")
            lines.append("")
            lines.append("| Threshold | Onset rate | Median turn | Q1 | Q3 |")
            lines.append("|---|---:|---:|---:|---:|")
            for threshold_key, payload in deficit_onset.items():
                loss = payload.get("losses", {})
                lines.append(
                    f"| <= {threshold_key} | {loss.get('onset_rate', 0.0):.2f} | {loss.get('median_turn', 0.0):.1f} | {loss.get('q1_turn', 0.0):.1f} | {loss.get('q3_turn', 0.0):.1f} |"
                )
            lines.append("")
        trajectory = cohort.get("trajectory_robustness", {})
        if trajectory:
            lines.append("#### Diagnostics: Trajectory Robustness")
            lines.append("")
            lines.append(
                "- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended."
            )
            lines.append(
                "- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses."
            )
            lines.append(
                "- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer."
            )
            lines.append(
                "- `Cross rate`: fraction of matches that ever fall below the threshold at least once."
            )
            lines.append(
                "- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold."
            )
            lines.append(
                "- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better."
            )
            lines.append(
                "- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes."
            )
            lines.append("")
            lines.append(
                f"- Max drawdown: mean {trajectory.get('max_drawdown', {}).get('mean', 0.0):.2f}, median {trajectory.get('max_drawdown', {}).get('median', 0.0):.2f}."
            )
            lines.append(
                f"- Drawdown span: mean {trajectory.get('drawdown_span_turns', {}).get('mean', 0.0):.2f} turns."
            )
            lines.append("")
            lines.append("| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |")
            lines.append("|---|---:|---:|---:|---:|---:|")
            for threshold_key, payload in trajectory.get("thresholds", {}).items():
                lines.append(
                    f"| <= {threshold_key} | {payload.get('mean_time_in_deficit_turns', 0.0):.2f} | {payload.get('mean_time_in_deficit_fraction', 0.0):.3f} | {payload.get('cross_rate', 0.0):.3f} | {payload.get('recovery_rate_after_cross', 0.0):.3f} | {payload.get('mean_recovery_latency_turns', 0.0):.2f} |"
                )
            lines.append("")
        contrasts = cohort.get("behavior_contrasts", {})
        if contrasts:
            lines.append("#### Diagnostics: Behavior Contrasts (win - loss)")
            lines.append("")
            lines.append(
                "- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`."
            )
            lines.append(
                "- Sign: positive means the behavior appears more in wins; negative means it appears more in losses."
            )
            lines.append(
                "- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible."
            )
            lines.append(
                "- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains."
            )
            lines.append(
                "- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches."
            )
            lines.append("")
            lines.append("| Metric | Delta | CI95 | Confidence |")
            lines.append("|---|---:|---|---|")
            for key, payload in contrasts.items():
                ci = payload.get("ci95", [0.0, 0.0])
                lines.append(
                    f"| `{key}` | {payload.get('delta', 0.0):+.3f} | [{ci[0]:+.3f}, {ci[1]:+.3f}] | {payload.get('confidence', 'insufficient_data')} |"
                )
            lines.append("")
        turning_points_payload = cohort.get("turning_points_summary", {})
        if "per_file" in turning_points_payload:
            turning_points = turning_points_payload.get("per_file", [])
            if turning_points:
                lines.append("#### Diagnostics: Top Turning Points (per match)")
                lines.append("- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.")
                lines.append("- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.")
                lines.append("- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.")
                for match_row in turning_points[:8]:
                    top_turns = match_row.get("top_turns", [])
                    if not top_turns:
                        continue
                    preview = ", ".join(
                        f"t{tp['turn']}:{tp['delta_change']:+.1f}/{tp['left_behind_turn']}/{tp['phase']}"
                        for tp in top_turns[:3]
                    )
                    lines.append(f"- `{match_row['match_id']}`: {preview}")
        else:
            lines.append("#### Diagnostics: Turning Points By Perspective")
            lines.append("- `self_inflicted` isolates bad swings on the selected player's own turns.")
            lines.append("- `opponent_swing` isolates bad swings created by the opponent's turns.")
            lines.append("- Values below use perspective-signed delta changes, so negative means bad for the selected side.")
            for label in ("self_inflicted", "opponent_swing"):
                match_rows = turning_points_payload.get(label, {}).get("per_file", [])
                if not match_rows:
                    continue
                lines.append(f"- `{label}`")
                for match_row in match_rows[:8]:
                    top_turns = match_row.get("top_turns", [])
                    if not top_turns:
                        continue
                    preview = ", ".join(
                        f"t{tp['turn']}:{tp['perspective_delta_change']:+.1f}/{tp['left_behind_turn']}/{tp['phase']}"
                        for tp in top_turns[:3]
                    )
                    lines.append(f"  - `{match_row['match_id']}`: {preview}")
        lines.append("")

    lines.append("# Batch Match Insights")
    lines.append("")
    lines.append("## Run Overview")
    lines.append(f"- Matches analyzed: **{insights['match_count']}**")
    lines.append(f"- Perspective: **{perspective}**")
    lines.append(f"- Minimum sample threshold (`n_min`): **{insights['n_min']}**")
    lines.append(
        f"- Deficit thresholds: `{', '.join(_format_threshold_key(v) for v in insights.get('deficit_thresholds', []))}`"
    )
    lines.append("")
    lines.append("## Prioritized Findings")
    lines.append(f"> Evidence-backed tuning leads from `{primary_cohort}`.")
    if insights["global_actions"]:
        for i, action in enumerate(insights["global_actions"], start=1):
            lines.append(f"{i}. {action}")
    else:
        lines.append("- No high-confidence global actions triggered.")
    lines.append("")
    lines.append("## Cohort Snapshot")
    lines.append("")
    lines.append("| Cohort | Type | N | Win Rate (CI95) | Mean Delta (CI95) | Search Conv (CI95) | Timeout | Catastrophic |")
    lines.append("|---|---|---:|---|---|---|---:|---:|")
    for cohort in ([display_global] if display_global else []):
        outcome = cohort["outcome"]
        behavior = cohort["behavior"]
        reliability = cohort["reliability"]
        lines.append(
            f"| `{cohort['cohort']}` | {cohort.get('cohort_type', 'global')} | {cohort['sample_size']} | {outcome['win_rate']:.3f} [{outcome['win_rate_ci95'][0]:.3f}, {outcome['win_rate_ci95'][1]:.3f}] | "
            f"{outcome['mean_score_delta']:+.2f} [{outcome['mean_score_delta_ci95'][0]:+.2f}, {outcome['mean_score_delta_ci95'][1]:+.2f}] | "
            f"{behavior['search_conversion_rate']:.3f} [{behavior['search_conversion_ci95'][0]:.3f}, {behavior['search_conversion_ci95'][1]:.3f}] | "
            f"{reliability['timeout_pressure_rate']:.3f} | {reliability['catastrophic_loss_rate']:.3f} |"
        )
    lines.append("")
    lines.append("## Cohort Details")
    if display_global:
        _append_cohort_details(display_global)
    if segment_cohorts:
        lines.append("## Stratified Cohort Insights and Analytics")
        lines.append("")
        lines.append("- Segment-level insights are grouped here to keep global findings focused and comparable.")
        lines.append("")
        lines.append("| Cohort | N | Win Rate (CI95) | Mean Delta (CI95) | Search Conv (CI95) |")
        lines.append("|---|---:|---|---|---|")
        for cohort in segment_cohorts:
            outcome = cohort["outcome"]
            behavior = cohort["behavior"]
            lines.append(
                f"| `{cohort['cohort']}` | {cohort['sample_size']} | {outcome['win_rate']:.3f} [{outcome['win_rate_ci95'][0]:.3f}, {outcome['win_rate_ci95'][1]:.3f}] | "
                f"{outcome['mean_score_delta']:+.2f} [{outcome['mean_score_delta_ci95'][0]:+.2f}, {outcome['mean_score_delta_ci95'][1]:+.2f}] | "
                f"{behavior['search_conversion_rate']:.3f} [{behavior['search_conversion_ci95'][0]:.3f}, {behavior['search_conversion_ci95'][1]:.3f}] |"
            )
        lines.append("")
        for cohort in segment_cohorts:
            _append_cohort_details(cohort)
    return "\n".join(lines).rstrip() + "\n"


def write_csv(insights: dict[str, Any], csv_path: Path) -> None:
    threshold_keys = [_format_threshold_key(float(v)) for v in insights.get("deficit_thresholds", [])]
    threshold_fieldnames: list[str] = []
    trajectory_fieldnames: list[str] = []
    for key in threshold_keys:
        threshold_fieldnames.extend([f"threshold_{key}_onset_rate", f"threshold_{key}_median_turn"])
        trajectory_fieldnames.extend([f"mean_time_in_deficit_{key}", f"recovery_rate_after_cross_{key}"])

    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "perspective",
                "cohort",
                "cohort_type",
                "opponent_archetype",
                "map_seed",
                "opening_family",
                "sample_size",
                "win_rate",
                "win_ci_lo",
                "win_ci_hi",
                "mean_score_delta",
                "delta_ci_lo",
                "delta_ci_hi",
                "search_conversion",
                "search_ci_lo",
                "search_ci_hi",
                "timeout_pressure_rate",
                "catastrophic_loss_rate",
                "early_delta_change",
                "mid_delta_change",
                "late_delta_change",
                *threshold_fieldnames,
                "top_transition_gap",
                "mean_max_drawdown",
                *trajectory_fieldnames,
                "search_conversion_delta",
                "search_conversion_delta_ci_lo",
                "search_conversion_delta_ci_hi",
                "actions",
            ],
        )
        writer.writeheader()
        for cohort in insights["cohorts"]:
            outcome = cohort["outcome"]
            behavior = cohort["behavior"]
            reliability = cohort["reliability"]
            phase_split = cohort.get("phase_split", {})
            top_transition = cohort.get("transition_patterns", {}).get("top_gaps", [])
            dimensions = cohort.get("cohort_dimensions", {})
            max_dd = cohort.get("trajectory_robustness", {}).get("max_drawdown", {}).get("mean", 0.0)
            sc = cohort.get("behavior_contrasts", {}).get("search_conversion_delta", {})
            sc_ci = sc.get("ci95", [0.0, 0.0])
            row = {
                "perspective": insights.get("perspective", "all"),
                "cohort": cohort["cohort"],
                "cohort_type": cohort.get("cohort_type", "global"),
                "opponent_archetype": dimensions.get("opponent_archetype", ""),
                "map_seed": dimensions.get("map_seed", ""),
                "opening_family": dimensions.get("opening_family", ""),
                "sample_size": cohort["sample_size"],
                "win_rate": outcome["win_rate"],
                "win_ci_lo": outcome["win_rate_ci95"][0],
                "win_ci_hi": outcome["win_rate_ci95"][1],
                "mean_score_delta": outcome["mean_score_delta"],
                "delta_ci_lo": outcome["mean_score_delta_ci95"][0],
                "delta_ci_hi": outcome["mean_score_delta_ci95"][1],
                "search_conversion": behavior["search_conversion_rate"],
                "search_ci_lo": behavior["search_conversion_ci95"][0],
                "search_ci_hi": behavior["search_conversion_ci95"][1],
                "timeout_pressure_rate": reliability["timeout_pressure_rate"],
                "catastrophic_loss_rate": reliability["catastrophic_loss_rate"],
                "early_delta_change": phase_split.get("losses", {}).get("early", {}).get("mean_delta_change", 0.0),
                "mid_delta_change": phase_split.get("losses", {}).get("mid", {}).get("mean_delta_change", 0.0),
                "late_delta_change": phase_split.get("losses", {}).get("late", {}).get("mean_delta_change", 0.0),
                "top_transition_gap": top_transition[0]["gap_abs"] if top_transition else 0.0,
                "mean_max_drawdown": max_dd,
                "search_conversion_delta": sc.get("delta", 0.0),
                "search_conversion_delta_ci_lo": sc_ci[0],
                "search_conversion_delta_ci_hi": sc_ci[1],
                "actions": " | ".join(cohort["actions"]),
            }
            deficit_onset = cohort.get("deficit_onset", {})
            trajectory_thresholds = cohort.get("trajectory_robustness", {}).get("thresholds", {})
            for key in threshold_keys:
                deficit = deficit_onset.get(key, {}).get("losses", {})
                traj = trajectory_thresholds.get(key, {})
                row[f"threshold_{key}_onset_rate"] = deficit.get("onset_rate", 0.0)
                row[f"threshold_{key}_median_turn"] = deficit.get("median_turn", 0.0)
                row[f"mean_time_in_deficit_{key}"] = traj.get("mean_time_in_deficit_turns", 0.0)
                row[f"recovery_rate_after_cross_{key}"] = traj.get("recovery_rate_after_cross", 0.0)
            writer.writerow(row)


def collect_match_files(match_root: Path) -> list[Path]:
    candidates = [path for path in match_root.rglob("*.json") if path.is_file()]
    return sorted(candidates)


def run_pipeline(
    match_root: Path,
    output_dir: Path,
    n_min: int,
    deficit_thresholds: list[float] | None = None,
    turning_point_k: int = 3,
    top_transitions: int = 8,
    transition_min_support: int = 5,
    max_fatal_rate: float = 0.0,
    stratify_by: list[str] | None = None,
    opening_horizon: int = 8,
    max_cohorts: int = 8,
    rare_min_support: int = 3,
    perspective: str = "all",
) -> int:
    files = collect_match_files(match_root)
    normalized: list[NormalizedMatch] = []
    parse_errors: list[dict[str, Any]] = []
    parse_warnings: list[dict[str, Any]] = []

    for file_path in files:
        match, issues = normalize_match(file_path)
        for issue in issues:
            event = {
                "path": str(file_path),
                "severity": issue.severity,
                "field": issue.field,
                "message": issue.message,
            }
            if issue.severity == "fatal":
                parse_errors.append(event)
            else:
                parse_warnings.append(event)
        if match is not None:
            normalized.append(match)

    output_dir.mkdir(parents=True, exist_ok=True)

    parse_report = {
        "match_root": str(match_root),
        "perspective": perspective,
        "file_count": len(files),
        "parsed_count": len(normalized),
        "fatal_count": len(parse_errors),
        "fatal_rate": (len(parse_errors) / len(files)) if files else 0.0,
        "max_fatal_rate": max_fatal_rate,
        "warning_count": len(parse_warnings),
        "fatal_issues": parse_errors,
        "warning_issues": parse_warnings,
    }
    (output_dir / "parse_report.json").write_text(json.dumps(parse_report, indent=2))
    if files and parse_report["fatal_rate"] > max_fatal_rate:
        print(
            f"Fatal parse rate {parse_report['fatal_rate']:.3f} exceeds max_fatal_rate={max_fatal_rate:.3f}; refusing insights generation."
        )
        return 2

    insights = build_insights(
        normalized,
        n_min=n_min,
        deficit_thresholds=deficit_thresholds,
        turning_point_k=turning_point_k,
        top_transitions=top_transitions,
        transition_min_support=transition_min_support,
        stratify_by=stratify_by,
        opening_horizon=opening_horizon,
        max_cohorts=max_cohorts,
        rare_min_support=rare_min_support,
        cohort_name=f"folder:{match_root.name}",
        perspective=perspective,
    )
    (output_dir / "insights_summary.json").write_text(json.dumps(insights, indent=2))
    (output_dir / "insights_report.md").write_text(render_markdown(insights))
    write_csv(insights, output_dir / "cohort_breakdown.csv")

    print(f"Analyzed {len(normalized)} matches from {len(files)} files.")
    print(f"Parse report: {output_dir / 'parse_report.json'}")
    print(f"Summary JSON: {output_dir / 'insights_summary.json'}")
    print(f"Report MD:    {output_dir / 'insights_report.md'}")
    print(f"Cohort CSV:   {output_dir / 'cohort_breakdown.csv'}")
    return 0 if normalized else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch parse match archives and derive high-confidence insights.")
    parser.add_argument(
        "--match-root",
        type=Path,
        default=DEFAULT_MATCH_ROOT,
        help=f"Directory containing match JSON files (default: {DEFAULT_MATCH_ROOT})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "reports" / "batch_match_insights",
        help="Directory for parse and insights artifacts.",
    )
    parser.add_argument("--n-min", type=int, default=8, help="Minimum sample size for high-confidence labeling.")
    parser.add_argument(
        "--perspective",
        choices=("a", "b", "all"),
        default="all",
        help="Behavior metric perspective: player A, player B, or the legacy mixed stream.",
    )
    parser.add_argument(
        "--deficit-thresholds",
        type=str,
        default="-5,-10,-15",
        help="Comma-separated score-delta thresholds for deficit onset analysis.",
    )
    parser.add_argument("--turning-point-k", type=int, default=3, help="Top K turning points per match.")
    parser.add_argument(
        "--report-top-transitions",
        type=int,
        default=8,
        help="Number of transition gap rows retained in structured output.",
    )
    parser.add_argument(
        "--transition-min-support",
        type=int,
        default=5,
        help="Minimum transition count support to include in transition diagnostics.",
    )
    parser.add_argument(
        "--stratify-by",
        type=str,
        default="opponent_archetype,map_seed,opening_family",
        help="Comma-separated derived cohort keys for segmentation.",
    )
    parser.add_argument(
        "--opening-horizon",
        type=int,
        default=8,
        help="Number of opening turns used for opening-family/signature derivation.",
    )
    parser.add_argument("--max-cohorts", type=int, default=8, help="Maximum number of stratified cohorts emitted.")
    parser.add_argument(
        "--rare-min-support",
        type=int,
        default=3,
        help="Per-dimension support below this value is collapsed into `other` before cohorting.",
    )
    parser.add_argument(
        "--max-fatal-rate",
        type=float,
        default=0.0,
        help="Maximum tolerated fraction of files with fatal parse issues before failing.",
    )
    args = parser.parse_args()
    thresholds = [float(part.strip()) for part in args.deficit_thresholds.split(",") if part.strip()]
    stratify_by = [part.strip() for part in args.stratify_by.split(",") if part.strip()]
    return run_pipeline(
        args.match_root,
        args.output_dir,
        n_min=args.n_min,
        deficit_thresholds=thresholds,
        turning_point_k=args.turning_point_k,
        top_transitions=args.report_top_transitions,
        transition_min_support=args.transition_min_support,
        max_fatal_rate=args.max_fatal_rate,
        stratify_by=stratify_by,
        opening_horizon=args.opening_horizon,
        max_cohorts=args.max_cohorts,
        rare_min_support=args.rare_min_support,
        perspective=args.perspective,
    )


if __name__ == "__main__":
    raise SystemExit(main())
