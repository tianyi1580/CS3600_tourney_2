#!/usr/bin/env python3
"""
Write m3_adaptation_clamp_verification_report.md (structured grid over adaptation.apply_adaptation).
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "3600-agents"))

from Yolanda.adaptation import (  # noqa: E402
    BASE_A,
    BASE_C,
    BASE_D,
    BASE_F,
    D_CLAMP_MARGIN,
    ENV_A,
    ENV_C,
    ENV_D,
    ENV_F,
    RawDeltas,
    apply_adaptation,
    compute_confidence,
)


def main() -> int:
    out_path = ROOT / "docs/m3_adaptation_clamp_verification_report.md"

    rows_md = []
    violations = []

    # Extreme raw deltas × confidence grid
    confs = [0.0, 0.34, 0.35, 0.5, 1.0]
    extremes = [
        RawDeltas(),
        RawDeltas(da=2, dc=2, dd=2, df=2, d_margin=2),
        RawDeltas(da=-2, dc=-2, dd=-2, df=-2, d_margin=-2),
    ]
    for conf, raw in itertools.product(confs, extremes):
        a, c, d, f, dm = apply_adaptation(conf, raw)
        if not (ENV_A[0] <= a <= ENV_A[1]):
            violations.append((conf, raw, "a", a))
        if not (ENV_C[0] <= c <= ENV_C[1]):
            violations.append((conf, raw, "c", c))
        if not (ENV_D[0] <= d <= ENV_D[1]):
            violations.append((conf, raw, "d", d))
        if not (ENV_F[0] <= f <= ENV_F[1]):
            violations.append((conf, raw, "f", f))
        if not (D_CLAMP_MARGIN[0] <= dm <= D_CLAMP_MARGIN[1]):
            violations.append((conf, raw, "dm", dm))
        rows_md.append(
            f"| {conf:.2f} | {raw.da:.1f},{raw.dc:.1f},{raw.dd:.1f},{raw.df:.1f},{raw.d_margin:.1f} | "
            f"{a:.4f} | {c:.4f} | {d:.4f} | {f:.4f} | {dm:+.4f} |"
        )

    conf_lines = "\n".join(
        f"| {t} | 0.25 | {compute_confidence(t, 0.25):.4f} |" for t in range(0, 16)
    )

    body = f"""# M3 adaptation clamp verification report

This report validates **bot_plan_v4** bounded adaptation: per-parameter delta clamps after confidence scaling,
absolute coefficient envelopes, and search-margin delta in `[{D_CLAMP_MARGIN[0]}, {D_CLAMP_MARGIN[1]}]`.

## Contracts checked

- Confidence: `confidence = clamp((observed_turns - 5) / 10, 0, 1) * (1 - behavior_entropy_norm)`.
- If `confidence < 0.35`, adaptive deltas are zero (coefficients revert to policy bases; margin delta `0`).
- Envelopes: `a ∈ {ENV_A}`, `c ∈ {ENV_C}`, `d ∈ {ENV_D}`, `f ∈ {ENV_F}` (absolute after adaptation).

## Grid: extreme RawDeltas × confidence

| conf | raw (da,dc,dd,df,dm) | a | c | d | f | margin_Δ |
| --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(rows_md)}

## Confidence vs observed_turns (entropy_norm=0.25)

| observed_turns | entropy_norm | confidence |
| --- | --- | --- |
{conf_lines}

## Violations

{"None — all sampled points satisfied envelopes and margin clamp." if not violations else str(violations)}

## Long-run note

v4 suggests aggregate clamp invariance over very long simulations; this file uses a **deterministic grid** over
`apply_adaptation` for reproducible CI evidence. Gameplay integration is covered by `tests/test_adaptation_*.py`
and `Yolanda.policy.PolicyEngine._observe_opponent_and_maybe_adapt`.

## Base coefficients (M2 defaults)

- BASE_A={BASE_A}, BASE_C={BASE_C}, BASE_D={BASE_D}, BASE_F={BASE_F}
"""
    out_path.write_text(body, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0 if not violations else 2


if __name__ == "__main__":
    raise SystemExit(main())
