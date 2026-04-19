# Batch Match Insights

## Run Overview
- Matches analyzed: **92**
- Minimum sample threshold (`n_min`): **8**
- Deficit thresholds: `-5, -10, -15`

## Prioritized Findings
> Evidence-backed tuning leads from `folder:yolanda_prime_v3_DO`.
1. Timeout pressure is elevated; tighten time budget caps and reduce expensive branches.
2. Search conversion is materially worse in losses; tighten belief threshold for SEARCH and raise fallback value floor before committing.
3. Early phase collapses in losses (mean delta change -3.44); tighten opening move safety and reduce high-variance branches in first third.

## Cohort Snapshot

| Cohort | Type | N | Win Rate (CI95) | Mean Delta (CI95) | Search Conv (CI95) | Timeout | Catastrophic |
|---|---|---:|---|---|---|---:|---:|
| `folder:yolanda_prime_v3_DO` | global | 92 | 0.527 [0.424, 0.630] | +0.21 [-2.05, +2.25] | 0.538 [0.511, 0.566] | 1.000 | 0.076 |

## Cohort Details
### folder:yolanda_prime_v3_DO

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.527 (CI95 [0.424, 0.630]) | medium_confidence |
| W/L/T | 48/43/1 | - |
| Mean score delta | +0.21 (CI95 [-2.05, +2.25]) | medium_confidence |
| Search conversion | 0.538 (CI95 [0.511, 0.566]) | high_confidence |
| Timeout pressure | 1.000 | - |
| Catastrophic loss | 0.076 (`final score delta <= -15 points`) | - |

#### Definitions
- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation
- Outcome direction is less stable; gather more matches before strong conclusions.

#### Loss Drivers
- PRIME rate (loss/win): 0.419 / 0.419
- Search conversion (loss/win): 0.491 / 0.586

#### Recommended Actions
1. Timeout pressure is elevated; tighten time budget caps and reduce expensive branches.
2. Search conversion is materially worse in losses; tighten belief threshold for SEARCH and raise fallback value floor before committing.
3. Early phase collapses in losses (mean delta change -3.44); tighten opening move safety and reduce high-variance branches in first third.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +1.88 | -3.44 | +2.00 |
| mid | +4.08 | +0.81 | -4.00 |
| late | +2.92 | -6.84 | +2.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->prime` | 1368 | 0.198 | 0.177 | 0.021 | win_heavier |
| `prime->search` | 516 | 0.063 | 0.080 | 0.017 | loss_heavier |
| `carpet->prime` | 401 | 0.049 | 0.062 | 0.014 | loss_heavier |
| `carpet->plain` | 257 | 0.041 | 0.029 | 0.012 | win_heavier |
| `plain->plain` | 530 | 0.078 | 0.067 | 0.012 | win_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 0.95 | 17.0 | 12.0 | 36.0 |
| <= -10 | 0.65 | 36.0 | 23.0 | 65.2 |
| <= -15 | 0.37 | 53.5 | 26.0 | 72.5 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 14.75, median 14.00.
- Drawdown span: mean 30.27 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 16.34 | 0.202 | 0.663 | 0.951 | 6.49 |
| <= -10 | 5.05 | 0.062 | 0.348 | 0.844 | 7.94 |
| <= -15 | 1.82 | 0.022 | 0.174 | 0.750 | 2.50 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | +0.085 | [+0.036, +0.133] | high_confidence |
| `prime_rate_delta` | -0.000 | [-0.015, +0.015] | medium_confidence |
| `search_rate_delta` | -0.023 | [-0.043, -0.008] | high_confidence |
| `carpet_rate_delta` | +0.006 | [-0.002, +0.014] | medium_confidence |
| `plain_rate_delta` | +0.017 | [+0.001, +0.033] | high_confidence |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (1)`: t12:-4.0/carpet/early, t24:-4.0/carpet/early, t34:-4.0/search/mid
- `match (10)`: t32:-6.0/carpet/mid, t12:-4.0/search/early, t52:-4.0/search/mid
- `match (11)`: t14:-4.0/carpet/early, t16:-4.0/carpet/early, t32:-4.0/search/mid
- `match (12)`: t74:-4.0/carpet/late, t14:-2.0/carpet/early, t18:-2.0/carpet/early
- `match (13)`: t10:-6.0/carpet/early, t38:-4.0/carpet/mid, t58:-4.0/search/late
- `match (14)`: t42:-6.0/carpet/mid, t36:-4.0/search/mid, t50:-4.0/carpet/mid
- `match (15)`: t16:-10.0/carpet/early, t36:-4.0/search/mid, t50:-4.0/search/mid
- `match (16)`: t16:-10.0/carpet/early, t36:-4.0/search/mid, t50:-4.0/search/mid

## Stratified Cohort Insights and Analytics

- Segment-level insights are grouped here to keep global findings focused and comparable.

| Cohort | N | Win Rate (CI95) | Mean Delta (CI95) | Search Conv (CI95) |
|---|---:|---|---|---|
| `segment:opponent_archetype=other,map_seed=other,opening_family=other` | 63 | 0.548 [0.421, 0.667] | +0.35 [-2.37, +3.02] | 0.532 [0.499, 0.565] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:7535860b,opening_family=prime_chain` | 4 | 0.750 [0.250, 1.000] | +6.50 [-3.50, +13.50] | 0.705 [0.558, 0.818] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:4eab2971,opening_family=prime_chain` | 4 | 0.250 [0.000, 0.750] | -7.25 [-17.00, +4.75] | 0.431 [0.312, 0.559] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:cca08ca8,opening_family=prime_chain` | 4 | 0.500 [0.000, 1.000] | -1.75 [-16.75, +13.00] | 0.520 [0.385, 0.652] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:d9b16026,opening_family=prime_chain` | 4 | 0.500 [0.000, 1.000] | -2.25 [-10.50, +6.00] | 0.587 [0.443, 0.717] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:28743561,opening_family=prime_chain` | 4 | 0.250 [0.000, 0.750] | -3.75 [-11.00, +7.75] | 0.549 [0.414, 0.677] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:2ac63c4b,opening_family=prime_chain` | 3 | 0.333 [0.000, 1.000] | -4.33 [-12.00, +5.00] | 0.611 [0.449, 0.752] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:3f80538d,opening_family=prime_chain` | 3 | 0.333 [0.000, 1.000] | -0.67 [-8.00, +14.00] | 0.549 [0.414, 0.677] |

### segment:opponent_archetype=other,map_seed=other,opening_family=other

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.548 (CI95 [0.421, 0.667]) | medium_confidence |
| W/L/T | 34/28/1 | - |
| Mean score delta | +0.35 (CI95 [-2.37, +3.02]) | medium_confidence |
| Search conversion | 0.532 (CI95 [0.499, 0.565]) | high_confidence |
| Timeout pressure | 1.000 | - |
| Catastrophic loss | 0.079 (`final score delta <= -15 points`) | - |

#### Definitions
- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation
- Outcome direction is less stable; gather more matches before strong conclusions.

#### Loss Drivers
- PRIME rate (loss/win): 0.416 / 0.423
- Search conversion (loss/win): 0.476 / 0.584

#### Recommended Actions
1. Timeout pressure is elevated; tighten time budget caps and reduce expensive branches.
2. Search conversion is materially worse in losses; tighten belief threshold for SEARCH and raise fallback value floor before committing.
3. Early phase collapses in losses (mean delta change -2.96); tighten opening move safety and reduce high-variance branches in first third.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +0.94 | -2.96 | +2.00 |
| mid | +4.15 | +1.79 | -4.00 |
| late | +2.88 | -7.71 | +2.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->prime` | 945 | 0.204 | 0.174 | 0.030 | win_heavier |
| `prime->search` | 347 | 0.061 | 0.081 | 0.021 | loss_heavier |
| `carpet->prime` | 258 | 0.044 | 0.061 | 0.017 | loss_heavier |
| `carpet->plain` | 171 | 0.042 | 0.026 | 0.016 | win_heavier |
| `search->prime` | 339 | 0.062 | 0.076 | 0.014 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 0.93 | 15.5 | 12.0 | 34.5 |
| <= -10 | 0.64 | 34.0 | 23.2 | 65.8 |
| <= -15 | 0.36 | 55.0 | 26.0 | 77.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 14.97, median 14.00.
- Drawdown span: mean 32.38 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 15.14 | 0.187 | 0.667 | 0.952 | 6.05 |
| <= -10 | 4.30 | 0.053 | 0.349 | 0.909 | 5.36 |
| <= -15 | 1.08 | 0.013 | 0.159 | 0.700 | 1.80 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | +0.095 | [+0.033, +0.153] | high_confidence |
| `prime_rate_delta` | +0.008 | [-0.009, +0.024] | medium_confidence |
| `search_rate_delta` | -0.027 | [-0.050, -0.006] | high_confidence |
| `carpet_rate_delta` | +0.008 | [-0.001, +0.018] | medium_confidence |
| `plain_rate_delta` | +0.011 | [-0.008, +0.032] | medium_confidence |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (1)`: t12:-4.0/carpet/early, t24:-4.0/carpet/early, t34:-4.0/search/mid
- `match (11)`: t14:-4.0/carpet/early, t16:-4.0/carpet/early, t32:-4.0/search/mid
- `match (48)`: t26:-6.0/carpet/early, t30:-4.0/search/mid, t74:-4.0/search/late
- `match (14)`: t42:-6.0/carpet/mid, t36:-4.0/search/mid, t50:-4.0/carpet/mid
- `match (47)`: t16:-10.0/carpet/early, t24:-4.0/carpet/early, t44:-4.0/search/mid
- `match (15)`: t16:-10.0/carpet/early, t36:-4.0/search/mid, t50:-4.0/search/mid
- `match (16)`: t16:-10.0/carpet/early, t36:-4.0/search/mid, t50:-4.0/search/mid
- `match (19)`: t80:-10.0/carpet/late, t2:-4.0/search/early, t18:-4.0/carpet/early

### segment:opponent_archetype=prime_heavy,map_seed=map:7535860b,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.750 (CI95 [0.250, 1.000]) | insufficient_data |
| W/L/T | 3/1/0 | - |
| Mean score delta | +6.50 (CI95 [-3.50, +13.50]) | insufficient_data |
| Search conversion | 0.705 (CI95 [0.558, 0.818]) | high_confidence |
| Timeout pressure | 1.000 | - |
| Catastrophic loss | 0.000 (`final score delta <= -15 points`) | - |

#### Definitions
- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation
- Outcome direction is less stable; gather more matches before strong conclusions.

#### Loss Drivers
- PRIME rate (loss/win): 0.444 / 0.412
- Search conversion (loss/win): 0.700 / 0.706

#### Recommended Actions
1. Early phase collapses in losses (mean delta change -4.00); tighten opening move safety and reduce high-variance branches in first third.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +0.00 | -4.00 | +0.00 |
| mid | +6.67 | +4.00 | +0.00 |
| late | +4.67 | -8.00 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `plain->plain` | 30 | 0.113 | 0.037 | 0.075 | win_heavier |
| `prime->prime` | 62 | 0.212 | 0.138 | 0.075 | win_heavier |
| `carpet->prime` | 20 | 0.046 | 0.113 | 0.067 | loss_heavier |
| `prime->plain` | 30 | 0.079 | 0.138 | 0.058 | loss_heavier |
| `prime->carpet` | 26 | 0.071 | 0.113 | 0.042 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 28.0 | 28.0 | 28.0 |
| <= -10 | 0.00 | 0.0 | 0.0 | 0.0 |
| <= -15 | 0.00 | 0.0 | 0.0 | 0.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 10.00, median 10.50.
- Drawdown span: mean 27.50 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 6.25 | 0.077 | 0.500 | 1.000 | 2.00 |
| <= -10 | 0.00 | 0.000 | 0.000 | 0.000 | 0.00 |
| <= -15 | 0.00 | 0.000 | 0.000 | 0.000 | 0.00 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | -0.004 | [-0.053, +0.069] | insufficient_data |
| `prime_rate_delta` | -0.033 | [-0.049, -0.025] | insufficient_data |
| `search_rate_delta` | +0.016 | [-0.004, +0.037] | insufficient_data |
| `carpet_rate_delta` | -0.021 | [-0.049, -0.004] | insufficient_data |
| `plain_rate_delta` | +0.037 | [+0.000, +0.062] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (12)`: t74:-4.0/carpet/late, t14:-2.0/carpet/early, t18:-2.0/carpet/early
- `match (52)`: t18:-10.0/carpet/early, t34:-4.0/search/mid, t46:-4.0/carpet/mid
- `match (60)`: t24:-6.0/carpet/early, t30:-4.0/search/mid, t44:-4.0/search/mid
- `match (4)`: t8:-4.0/search/early, t26:-4.0/search/early, t28:-4.0/search/mid

### segment:opponent_archetype=prime_heavy,map_seed=map:4eab2971,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.250 (CI95 [0.000, 0.750]) | insufficient_data |
| W/L/T | 1/3/0 | - |
| Mean score delta | -7.25 (CI95 [-17.00, +4.75]) | insufficient_data |
| Search conversion | 0.431 (CI95 [0.312, 0.559]) | high_confidence |
| Timeout pressure | 1.000 | - |
| Catastrophic loss | 0.250 (`final score delta <= -15 points`) | - |

#### Definitions
- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation
- Outcome direction is less stable; gather more matches before strong conclusions.
- Elevated catastrophic loss risk; prioritize guardrails in losing trajectories.

#### Loss Drivers
- PRIME rate (loss/win): 0.403 / 0.370
- Search conversion (loss/win): 0.477 / 0.286

#### Recommended Actions
1. Early phase collapses in losses (mean delta change -9.00); tighten opening move safety and reduce high-variance branches in first third.
2. Transition `search->prime` is loss-heavier (gap 0.050); revisit policy thresholds governing this move switch.
3. Deficit onset below -10 happens early in losses (rate 1.00, median turn 16.0); increase early recovery bias and defensive search discipline.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +4.00 | -9.00 | +0.00 |
| mid | +1.00 | -1.00 | +0.00 |
| late | +5.00 | -3.00 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `search->prime` | 20 | 0.025 | 0.075 | 0.050 | loss_heavier |
| `prime->search` | 24 | 0.037 | 0.087 | 0.050 | loss_heavier |
| `prime->plain` | 37 | 0.150 | 0.104 | 0.046 | win_heavier |
| `plain->plain` | 30 | 0.125 | 0.083 | 0.042 | win_heavier |
| `search->search` | 14 | 0.075 | 0.033 | 0.042 | win_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 12.0 | 11.0 | 17.0 |
| <= -10 | 1.00 | 16.0 | 14.0 | 41.0 |
| <= -15 | 0.67 | 45.5 | 32.2 | 58.8 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 20.00, median 20.50.
- Drawdown span: mean 38.00 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 34.25 | 0.423 | 1.000 | 0.750 | 20.25 |
| <= -10 | 21.75 | 0.269 | 0.750 | 0.667 | 22.67 |
| <= -15 | 16.00 | 0.198 | 0.500 | 0.500 | 5.00 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | -0.187 | [-0.381, -0.048] | insufficient_data |
| `prime_rate_delta` | -0.033 | [-0.058, -0.008] | insufficient_data |
| `search_rate_delta` | -0.008 | [-0.049, +0.025] | insufficient_data |
| `carpet_rate_delta` | -0.029 | [-0.037, -0.012] | insufficient_data |
| `plain_rate_delta` | +0.070 | [+0.062, +0.086] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (13)`: t10:-6.0/carpet/early, t38:-4.0/carpet/mid, t58:-4.0/search/late
- `match (44)`: t16:-4.0/carpet/early, t20:-4.0/search/early, t38:-4.0/carpet/mid
- `match (6)`: t12:-10.0/carpet/early, t28:-4.0/search/mid, t50:-4.0/search/mid
- `match (63)`: t22:-6.0/carpet/early, t32:-4.0/carpet/mid, t7:-2.0/search/early

### segment:opponent_archetype=prime_heavy,map_seed=map:cca08ca8,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.500 (CI95 [0.000, 1.000]) | insufficient_data |
| W/L/T | 2/2/0 | - |
| Mean score delta | -1.75 (CI95 [-16.75, +13.00]) | insufficient_data |
| Search conversion | 0.520 (CI95 [0.385, 0.652]) | high_confidence |
| Timeout pressure | 1.000 | - |
| Catastrophic loss | 0.250 (`final score delta <= -15 points`) | - |

#### Definitions
- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation
- Outcome direction is less stable; gather more matches before strong conclusions.
- Elevated catastrophic loss risk; prioritize guardrails in losing trajectories.

#### Loss Drivers
- PRIME rate (loss/win): 0.444 / 0.395
- Search conversion (loss/win): 0.583 / 0.462

#### Recommended Actions
1. Transition `prime->plain` is loss-heavier (gap 0.038); revisit policy thresholds governing this move switch.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +3.00 | -1.50 | +0.00 |
| mid | +2.00 | -4.50 | +0.00 |
| late | +5.50 | -8.00 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->plain` | 34 | 0.087 | 0.125 | 0.038 | loss_heavier |
| `plain->plain` | 32 | 0.119 | 0.081 | 0.037 | win_heavier |
| `search->plain` | 15 | 0.062 | 0.031 | 0.031 | win_heavier |
| `carpet->prime` | 18 | 0.044 | 0.069 | 0.025 | loss_heavier |
| `prime->search` | 26 | 0.069 | 0.094 | 0.025 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 23.0 | 22.5 | 23.5 |
| <= -10 | 0.50 | 49.0 | 49.0 | 49.0 |
| <= -15 | 0.50 | 52.0 | 52.0 | 52.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 16.00, median 12.50.
- Drawdown span: mean 29.75 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 18.50 | 0.228 | 0.750 | 1.000 | 2.33 |
| <= -10 | 8.00 | 0.099 | 0.250 | 0.000 | 31.00 |
| <= -15 | 7.00 | 0.086 | 0.250 | 1.000 | 5.00 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | -0.138 | [-0.282, +0.005] | insufficient_data |
| `prime_rate_delta` | -0.049 | [-0.111, +0.012] | insufficient_data |
| `search_rate_delta` | +0.012 | [-0.025, +0.049] | insufficient_data |
| `carpet_rate_delta` | +0.000 | [-0.025, +0.025] | insufficient_data |
| `plain_rate_delta` | +0.037 | [-0.012, +0.086] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (21)`: t24:-4.0/carpet/early, t34:-4.0/search/mid, t46:-4.0/search/mid
- `match (39)`: t10:-4.0/carpet/early, t12:-4.0/search/early, t36:-4.0/carpet/mid
- `match (4)`: t10:-4.0/carpet/early, t18:-4.0/search/early, t40:-4.0/search/mid
- `match (58)`: t22:-6.0/carpet/early, t8:-4.0/carpet/early, t30:-4.0/carpet/mid

### segment:opponent_archetype=prime_heavy,map_seed=map:d9b16026,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.500 (CI95 [0.000, 1.000]) | insufficient_data |
| W/L/T | 2/2/0 | - |
| Mean score delta | -2.25 (CI95 [-10.50, +6.00]) | insufficient_data |
| Search conversion | 0.587 (CI95 [0.443, 0.717]) | high_confidence |
| Timeout pressure | 1.000 | - |
| Catastrophic loss | 0.000 (`final score delta <= -15 points`) | - |

#### Definitions
- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation
- Outcome direction is less stable; gather more matches before strong conclusions.

#### Loss Drivers
- PRIME rate (loss/win): 0.488 / 0.420
- Search conversion (loss/win): 0.458 / 0.727

#### Recommended Actions
1. Search conversion is materially worse in losses; tighten belief threshold for SEARCH and raise fallback value floor before committing.
2. Early phase collapses in losses (mean delta change -5.50); tighten opening move safety and reduce high-variance branches in first third.
3. Transition `prime->prime` is loss-heavier (gap 0.075); revisit policy thresholds governing this move switch.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +4.50 | -5.50 | +0.00 |
| mid | +3.00 | -1.00 | +0.00 |
| late | -1.50 | -4.00 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->prime` | 68 | 0.175 | 0.250 | 0.075 | loss_heavier |
| `plain->plain` | 14 | 0.075 | 0.013 | 0.062 | win_heavier |
| `plain->carpet` | 13 | 0.056 | 0.025 | 0.031 | win_heavier |
| `prime->carpet` | 22 | 0.056 | 0.081 | 0.025 | loss_heavier |
| `carpet->carpet` | 8 | 0.013 | 0.037 | 0.025 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 17.0 | 16.5 | 17.5 |
| <= -10 | 1.00 | 29.5 | 26.2 | 32.8 |
| <= -15 | 0.50 | 44.0 | 44.0 | 44.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 13.25, median 12.50.
- Drawdown span: mean 17.00 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 27.00 | 0.333 | 0.500 | 1.000 | 2.00 |
| <= -10 | 8.25 | 0.102 | 0.500 | 1.000 | 4.50 |
| <= -15 | 0.75 | 0.009 | 0.250 | 1.000 | 3.00 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | +0.260 | [+0.205, +0.315] | insufficient_data |
| `prime_rate_delta` | -0.068 | [-0.099, -0.037] | insufficient_data |
| `search_rate_delta` | -0.012 | [-0.049, +0.025] | insufficient_data |
| `carpet_rate_delta` | -0.025 | [-0.049, +0.000] | insufficient_data |
| `plain_rate_delta` | +0.105 | [+0.049, +0.160] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (24)`: t36:-6.0/carpet/mid, t16:-4.0/carpet/early, t40:-4.0/search/mid
- `match (64)`: t50:-4.0/search/mid, t66:-4.0/search/late, t68:-4.0/carpet/late
- `match (68)`: t6:-4.0/carpet/early, t70:-4.0/carpet/late, t74:-4.0/search/late
- `match (13)`: t16:-10.0/carpet/early, t56:-4.0/carpet/late, t19:-2.0/search/early

### segment:opponent_archetype=prime_heavy,map_seed=map:28743561,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.250 (CI95 [0.000, 0.750]) | insufficient_data |
| W/L/T | 1/3/0 | - |
| Mean score delta | -3.75 (CI95 [-11.00, +7.75]) | insufficient_data |
| Search conversion | 0.549 (CI95 [0.414, 0.677]) | high_confidence |
| Timeout pressure | 1.000 | - |
| Catastrophic loss | 0.000 (`final score delta <= -15 points`) | - |

#### Definitions
- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation
- Outcome direction is less stable; gather more matches before strong conclusions.

#### Loss Drivers
- PRIME rate (loss/win): 0.432 / 0.469
- Search conversion (loss/win): 0.523 / 0.714

#### Recommended Actions
1. Search conversion is materially worse in losses; tighten belief threshold for SEARCH and raise fallback value floor before committing.
2. Early phase collapses in losses (mean delta change -3.00); tighten opening move safety and reduce high-variance branches in first third.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +2.00 | -3.00 | +0.00 |
| mid | +15.00 | +2.33 | +0.00 |
| late | -4.00 | -8.67 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->plain` | 33 | 0.150 | 0.087 | 0.062 | win_heavier |
| `plain->carpet` | 13 | 0.075 | 0.029 | 0.046 | win_heavier |
| `carpet->prime` | 22 | 0.100 | 0.058 | 0.042 | win_heavier |
| `prime->search` | 26 | 0.050 | 0.092 | 0.042 | loss_heavier |
| `search->search` | 7 | 0.000 | 0.029 | 0.029 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 46.0 | 28.0 | 46.0 |
| <= -10 | 0.33 | 24.0 | 24.0 | 24.0 |
| <= -15 | 0.33 | 65.0 | 65.0 | 65.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 16.25, median 17.00.
- Drawdown span: mean 25.25 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 20.75 | 0.256 | 1.000 | 1.000 | 1.00 |
| <= -10 | 5.25 | 0.065 | 0.250 | 1.000 | 11.00 |
| <= -15 | 0.50 | 0.006 | 0.250 | 1.000 | 2.00 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | +0.198 | [+0.181, +0.214] | insufficient_data |
| `prime_rate_delta` | +0.037 | [-0.000, +0.074] | insufficient_data |
| `search_rate_delta` | -0.095 | [-0.128, -0.062] | insufficient_data |
| `carpet_rate_delta` | +0.016 | [+0.012, +0.021] | insufficient_data |
| `plain_rate_delta` | +0.041 | [+0.033, +0.049] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (51)`: t24:-6.0/carpet/early, t10:-4.0/carpet/early, t22:-4.0/search/early
- `match (5)`: t10:-4.0/carpet/early, t20:-4.0/carpet/early, t54:-4.0/carpet/late
- `match (10)`: t46:-10.0/carpet/mid, t24:-4.0/search/early, t52:-4.0/search/mid
- `match (11)`: t46:-10.0/carpet/mid, t24:-4.0/search/early, t52:-4.0/search/mid

### segment:opponent_archetype=prime_heavy,map_seed=map:2ac63c4b,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.333 (CI95 [0.000, 1.000]) | insufficient_data |
| W/L/T | 1/2/0 | - |
| Mean score delta | -4.33 (CI95 [-12.00, +5.00]) | insufficient_data |
| Search conversion | 0.611 (CI95 [0.449, 0.752]) | high_confidence |
| Timeout pressure | 1.000 | - |
| Catastrophic loss | 0.000 (`final score delta <= -15 points`) | - |

#### Definitions
- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation
- Outcome direction is less stable; gather more matches before strong conclusions.

#### Loss Drivers
- PRIME rate (loss/win): 0.438 / 0.383
- Search conversion (loss/win): 0.600 / 0.625

#### Recommended Actions
1. Early phase collapses in losses (mean delta change -6.00); tighten opening move safety and reduce high-variance branches in first third.
2. Transition `prime->prime` is loss-heavier (gap 0.094); revisit policy thresholds governing this move switch.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +5.00 | -6.00 | +0.00 |
| mid | +0.00 | +3.50 | +0.00 |
| late | +0.00 | -6.50 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->prime` | 45 | 0.125 | 0.219 | 0.094 | loss_heavier |
| `prime->search` | 14 | 0.113 | 0.031 | 0.081 | win_heavier |
| `plain->plain` | 19 | 0.113 | 0.062 | 0.050 | win_heavier |
| `search->prime` | 11 | 0.075 | 0.031 | 0.044 | win_heavier |
| `plain->carpet` | 7 | 0.000 | 0.044 | 0.044 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 31.0 | 23.5 | 38.5 |
| <= -10 | 0.50 | 80.0 | 80.0 | 80.0 |
| <= -15 | 0.00 | 0.0 | 0.0 | 0.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 12.33, median 12.00.
- Drawdown span: mean 29.00 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 12.67 | 0.156 | 0.667 | 1.000 | 4.00 |
| <= -10 | 0.33 | 0.004 | 0.333 | 0.000 | 0.00 |
| <= -15 | 0.00 | 0.000 | 0.000 | 0.000 | 0.00 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | +0.021 | [+0.000, +0.042] | insufficient_data |
| `prime_rate_delta` | -0.056 | [-0.074, -0.037] | insufficient_data |
| `search_rate_delta` | +0.074 | [+0.049, +0.099] | insufficient_data |
| `carpet_rate_delta` | -0.012 | [-0.012, -0.012] | insufficient_data |
| `plain_rate_delta` | -0.006 | [-0.012, +0.000] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (10)`: t32:-6.0/carpet/mid, t12:-4.0/search/early, t52:-4.0/search/mid
- `match (56)`: t14:-4.0/carpet/early, t16:-4.0/carpet/early, t26:-4.0/search/early
- `match (8)`: t22:-4.0/carpet/early, t24:-4.0/carpet/early, t40:-4.0/carpet/mid

### segment:opponent_archetype=prime_heavy,map_seed=map:3f80538d,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.333 (CI95 [0.000, 1.000]) | insufficient_data |
| W/L/T | 1/2/0 | - |
| Mean score delta | -0.67 (CI95 [-8.00, +14.00]) | insufficient_data |
| Search conversion | 0.549 (CI95 [0.414, 0.677]) | high_confidence |
| Timeout pressure | 1.000 | - |
| Catastrophic loss | 0.000 (`final score delta <= -15 points`) | - |

#### Definitions
- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation
- Outcome direction is less stable; gather more matches before strong conclusions.

#### Loss Drivers
- PRIME rate (loss/win): 0.352 / 0.420
- Search conversion (loss/win): 0.487 / 0.750

#### Recommended Actions
1. Search conversion is materially worse in losses; tighten belief threshold for SEARCH and raise fallback value floor before committing.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +8.00 | +0.50 | +0.00 |
| mid | +3.00 | -9.50 | +0.00 |
| late | +3.00 | +1.00 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->prime` | 35 | 0.212 | 0.113 | 0.100 | win_heavier |
| `prime->plain` | 17 | 0.037 | 0.087 | 0.050 | loss_heavier |
| `carpet->plain` | 8 | 0.062 | 0.019 | 0.044 | win_heavier |
| `search->search` | 7 | 0.000 | 0.044 | 0.044 | loss_heavier |
| `plain->search` | 15 | 0.037 | 0.075 | 0.037 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 22.0 | 15.0 | 29.0 |
| <= -10 | 1.00 | 41.0 | 40.0 | 42.0 |
| <= -15 | 0.50 | 55.0 | 55.0 | 55.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 16.33, median 15.00.
- Drawdown span: mean 27.67 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 28.00 | 0.346 | 0.667 | 1.000 | 17.00 |
| <= -10 | 6.67 | 0.082 | 0.667 | 1.000 | 8.50 |
| <= -15 | 0.67 | 0.008 | 0.333 | 1.000 | 2.00 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | +0.263 | [+0.250, +0.276] | insufficient_data |
| `prime_rate_delta` | +0.068 | [+0.037, +0.099] | insufficient_data |
| `search_rate_delta` | -0.093 | [-0.099, -0.086] | insufficient_data |
| `carpet_rate_delta` | +0.031 | [+0.025, +0.037] | insufficient_data |
| `plain_rate_delta` | -0.006 | [-0.037, +0.025] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (17)`: t4:-4.0/search/early, t16:-4.0/carpet/early, t26:-4.0/search/early
- `match (25)`: t40:-4.0/carpet/mid, t42:-4.0/search/mid, t50:-4.0/search/mid
- `match (28)`: t30:-4.0/search/mid, t36:-4.0/search/mid, t74:-4.0/carpet/late
