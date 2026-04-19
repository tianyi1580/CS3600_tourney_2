# M3 adaptation clamp verification report

This report validates **bot_plan_v4** bounded adaptation: per-parameter delta clamps after confidence scaling,
absolute coefficient envelopes, and search-margin delta in `[-0.05, 0.1]`.

## Contracts checked

- Confidence: `confidence = clamp((observed_turns - 5) / 10, 0, 1) * (1 - behavior_entropy_norm)`.
- If `confidence < 0.35`, adaptive deltas are zero (coefficients revert to policy bases; margin delta `0`).
- Envelopes: `a ∈ (0.8, 1.2)`, `c ∈ (0.45, 0.75)`, `d ∈ (0.2, 0.55)`, `f ∈ (0.55, 0.95)` (absolute after adaptation).

## Grid: extreme RawDeltas × confidence

| conf | raw (da,dc,dd,df,dm) | a | c | d | f | margin_Δ |
| --- | --- | --- | --- | --- | --- | --- |
| 0.00 | 0.0,0.0,0.0,0.0,0.0 | 1.0000 | 0.6000 | 0.3500 | 0.7500 | +0.0000 |
| 0.00 | 2.0,2.0,2.0,2.0,2.0 | 1.0000 | 0.6000 | 0.3500 | 0.7500 | +0.0000 |
| 0.00 | -2.0,-2.0,-2.0,-2.0,-2.0 | 1.0000 | 0.6000 | 0.3500 | 0.7500 | +0.0000 |
| 0.34 | 0.0,0.0,0.0,0.0,0.0 | 1.0000 | 0.6000 | 0.3500 | 0.7500 | +0.0000 |
| 0.34 | 2.0,2.0,2.0,2.0,2.0 | 1.0000 | 0.6000 | 0.3500 | 0.7500 | +0.0000 |
| 0.34 | -2.0,-2.0,-2.0,-2.0,-2.0 | 1.0000 | 0.6000 | 0.3500 | 0.7500 | +0.0000 |
| 0.35 | 0.0,0.0,0.0,0.0,0.0 | 1.0000 | 0.6000 | 0.3500 | 0.7500 | +0.0000 |
| 0.35 | 2.0,2.0,2.0,2.0,2.0 | 1.1000 | 0.7000 | 0.5000 | 0.8500 | +0.1000 |
| 0.35 | -2.0,-2.0,-2.0,-2.0,-2.0 | 0.9000 | 0.5000 | 0.2000 | 0.6500 | -0.0500 |
| 0.50 | 0.0,0.0,0.0,0.0,0.0 | 1.0000 | 0.6000 | 0.3500 | 0.7500 | +0.0000 |
| 0.50 | 2.0,2.0,2.0,2.0,2.0 | 1.1000 | 0.7000 | 0.5000 | 0.8500 | +0.1000 |
| 0.50 | -2.0,-2.0,-2.0,-2.0,-2.0 | 0.9000 | 0.5000 | 0.2000 | 0.6500 | -0.0500 |
| 1.00 | 0.0,0.0,0.0,0.0,0.0 | 1.0000 | 0.6000 | 0.3500 | 0.7500 | +0.0000 |
| 1.00 | 2.0,2.0,2.0,2.0,2.0 | 1.1000 | 0.7000 | 0.5000 | 0.8500 | +0.1000 |
| 1.00 | -2.0,-2.0,-2.0,-2.0,-2.0 | 0.9000 | 0.5000 | 0.2000 | 0.6500 | -0.0500 |

## Confidence vs observed_turns (entropy_norm=0.25)

| observed_turns | entropy_norm | confidence |
| --- | --- | --- |
| 0 | 0.25 | 0.0000 |
| 1 | 0.25 | 0.0000 |
| 2 | 0.25 | 0.0000 |
| 3 | 0.25 | 0.0000 |
| 4 | 0.25 | 0.0000 |
| 5 | 0.25 | 0.0000 |
| 6 | 0.25 | 0.0750 |
| 7 | 0.25 | 0.1500 |
| 8 | 0.25 | 0.2250 |
| 9 | 0.25 | 0.3000 |
| 10 | 0.25 | 0.3750 |
| 11 | 0.25 | 0.4500 |
| 12 | 0.25 | 0.5250 |
| 13 | 0.25 | 0.6000 |
| 14 | 0.25 | 0.6750 |
| 15 | 0.25 | 0.7500 |

## Violations

None — all sampled points satisfied envelopes and margin clamp.

## Long-run note

v4 suggests aggregate clamp invariance over very long simulations; this file uses a **deterministic grid** over
`apply_adaptation` for reproducible CI evidence. Gameplay integration is covered by `tests/test_adaptation_*.py`
and `Yolanda.policy.PolicyEngine._observe_opponent_and_maybe_adapt`.

## Base coefficients (M2 defaults)

- BASE_A=1.0, BASE_C=0.6, BASE_D=0.35, BASE_F=0.75
