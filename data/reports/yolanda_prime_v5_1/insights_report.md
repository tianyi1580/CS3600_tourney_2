# Batch Match Insights

## Run Overview
- Matches analyzed: **50**
- Minimum sample threshold (`n_min`): **8**
- Deficit thresholds: `-5, -10, -15`

## Prioritized Findings
> Evidence-backed tuning leads from `folder:yolanda_prime_v5_1`.
- No high-confidence global actions triggered.

## Cohort Snapshot

| Cohort | Type | N | Win Rate (CI95) | Mean Delta (CI95) | Search Conv (CI95) | Timeout | Catastrophic |
|---|---|---:|---|---|---|---:|---:|
| `folder:yolanda_prime_v5_1` | global | 50 | 0.410 [0.280, 0.550] | -1.42 [-4.48, +1.80] | 0.584 [0.542, 0.625] | 0.000 | 0.100 |

## Cohort Details
### folder:yolanda_prime_v5_1

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.410 (CI95 [0.280, 0.550]) | medium_confidence |
| W/L/T | 20/29/1 | - |
| Mean score delta | -1.42 (CI95 [-4.48, +1.80]) | medium_confidence |
| Search conversion | 0.584 (CI95 [0.542, 0.625]) | high_confidence |
| Timeout pressure | 0.000 | - |
| Catastrophic loss | 0.100 (`final score delta <= -15 points`) | - |

#### Definitions
- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation
- Outcome direction is less stable; gather more matches before strong conclusions.

#### Loss Drivers
- PRIME rate (loss/win): 0.441 / 0.419
- Search conversion (loss/win): 0.584 / 0.580

#### Recommended Actions
- None

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +2.55 | -0.17 | +7.00 |
| mid | +6.65 | -4.55 | -1.00 |
| late | -0.15 | -3.97 | -6.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->prime` | 748 | 0.176 | 0.201 | 0.025 | loss_heavier |
| `search->prime` | 232 | 0.069 | 0.052 | 0.017 | win_heavier |
| `plain->prime` | 487 | 0.116 | 0.130 | 0.015 | loss_heavier |
| `plain->search` | 156 | 0.048 | 0.034 | 0.013 | win_heavier |
| `prime->search` | 232 | 0.066 | 0.055 | 0.011 | win_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 0.90 | 33.0 | 18.2 | 45.5 |
| <= -10 | 0.59 | 40.0 | 32.0 | 64.0 |
| <= -15 | 0.31 | 58.0 | 38.0 | 74.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 14.52, median 13.00.
- Drawdown span: mean 32.66 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 16.80 | 0.207 | 0.700 | 0.886 | 7.97 |
| <= -10 | 7.76 | 0.096 | 0.380 | 0.842 | 10.68 |
| <= -15 | 2.88 | 0.036 | 0.180 | 0.778 | 7.44 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | -0.027 | [-0.125, +0.082] | medium_confidence |
| `prime_rate_delta` | -0.022 | [-0.036, -0.008] | high_confidence |
| `search_rate_delta` | +0.023 | [+0.004, +0.041] | high_confidence |
| `carpet_rate_delta` | -0.010 | [-0.020, -0.001] | high_confidence |
| `plain_rate_delta` | +0.010 | [-0.010, +0.031] | medium_confidence |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match - 2026-04-19T210028.130`: t20:-4.0/search/early, t42:-4.0/search/mid, t68:-4.0/search/late
- `match - 2026-04-19T210038.368`: t28:-4.0/search/mid, t46:-4.0/carpet/mid, t50:-4.0/carpet/mid
- `match - 2026-04-19T210056.221`: t24:-4.0/search/early, t32:-4.0/search/mid, t36:-4.0/search/mid
- `match - 2026-04-19T210110.980`: t28:-4.0/search/mid, t32:-4.0/search/mid, t50:-4.0/search/mid
- `match - 2026-04-19T210119.467`: t10:-6.0/carpet/early, t20:-4.0/carpet/early, t24:-4.0/search/early
- `match - 2026-04-19T210126.579`: t28:-4.0/search/mid, t32:-4.0/search/mid, t36:-4.0/carpet/mid
- `match - 2026-04-19T210133.832`: t42:-4.0/search/mid, t64:-4.0/search/late, t68:-4.0/search/late
- `match - 2026-04-19T210139.227`: t6:-4.0/search/early, t18:-4.0/carpet/early, t36:-4.0/search/mid

## Stratified Cohort Insights and Analytics

- Segment-level insights are grouped here to keep global findings focused and comparable.

| Cohort | N | Win Rate (CI95) | Mean Delta (CI95) | Search Conv (CI95) |
|---|---:|---|---|---|
| `segment:opponent_archetype=other,map_seed=other,opening_family=other` | 44 | 0.420 [0.273, 0.557] | -1.34 [-4.64, +2.00] | 0.568 [0.523, 0.612] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:d256afbc,opening_family=prime_chain` | 3 | 0.333 [0.000, 1.000] | -1.00 [-9.00, +8.00] | 0.722 [0.560, 0.842] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:f6a92a2b,opening_family=prime_chain` | 3 | 0.333 [0.000, 1.000] | -3.00 [-12.00, +4.00] | 0.679 [0.493, 0.821] |

### segment:opponent_archetype=other,map_seed=other,opening_family=other

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.420 (CI95 [0.273, 0.557]) | medium_confidence |
| W/L/T | 18/25/1 | - |
| Mean score delta | -1.34 (CI95 [-4.64, +2.00]) | medium_confidence |
| Search conversion | 0.568 (CI95 [0.523, 0.612]) | high_confidence |
| Timeout pressure | 0.000 | - |
| Catastrophic loss | 0.114 (`final score delta <= -15 points`) | - |

#### Definitions
- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation
- Outcome direction is less stable; gather more matches before strong conclusions.

#### Loss Drivers
- PRIME rate (loss/win): 0.444 / 0.421
- Search conversion (loss/win): 0.561 / 0.571

#### Recommended Actions
- None

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +1.89 | -0.28 | +7.00 |
| mid | +7.56 | -4.32 | -1.00 |
| late | -0.06 | -4.52 | -6.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->prime` | 672 | 0.179 | 0.207 | 0.028 | loss_heavier |
| `plain->plain` | 263 | 0.086 | 0.070 | 0.017 | win_heavier |
| `plain->prime` | 421 | 0.113 | 0.129 | 0.016 | loss_heavier |
| `search->prime` | 206 | 0.069 | 0.053 | 0.015 | win_heavier |
| `plain->search` | 135 | 0.047 | 0.034 | 0.013 | win_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 0.88 | 32.0 | 15.0 | 43.0 |
| <= -10 | 0.60 | 36.0 | 32.0 | 59.0 |
| <= -15 | 0.32 | 50.0 | 37.5 | 74.5 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 14.61, median 13.00.
- Drawdown span: mean 31.75 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 16.95 | 0.209 | 0.705 | 0.871 | 8.52 |
| <= -10 | 8.23 | 0.102 | 0.386 | 0.824 | 11.35 |
| <= -15 | 3.20 | 0.040 | 0.182 | 0.750 | 8.00 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | -0.009 | [-0.121, +0.111] | medium_confidence |
| `prime_rate_delta` | -0.023 | [-0.039, -0.009] | high_confidence |
| `search_rate_delta` | +0.018 | [-0.000, +0.037] | medium_confidence |
| `carpet_rate_delta` | -0.013 | [-0.023, -0.002] | high_confidence |
| `plain_rate_delta` | +0.018 | [-0.005, +0.037] | medium_confidence |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match - 2026-04-19T210028.130`: t20:-4.0/search/early, t42:-4.0/search/mid, t68:-4.0/search/late
- `match - 2026-04-19T210410.510`: t32:-4.0/search/mid, t42:-4.0/search/mid, t50:-4.0/carpet/mid
- `match - 2026-04-19T210038.368`: t28:-4.0/search/mid, t46:-4.0/carpet/mid, t50:-4.0/carpet/mid
- `match - 2026-04-19T210119.467`: t10:-6.0/carpet/early, t20:-4.0/carpet/early, t24:-4.0/search/early
- `match - 2026-04-19T210126.579`: t28:-4.0/search/mid, t32:-4.0/search/mid, t36:-4.0/carpet/mid
- `match - 2026-04-19T210510.891`: t10:-4.0/carpet/early, t24:-4.0/search/early, t34:-4.0/carpet/mid
- `match - 2026-04-19T210133.832`: t42:-4.0/search/mid, t64:-4.0/search/late, t68:-4.0/search/late
- `match - 2026-04-19T210503.611`: t34:-6.0/carpet/mid, t20:-4.0/carpet/early, t22:-4.0/search/early

### segment:opponent_archetype=prime_heavy,map_seed=map:d256afbc,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.333 (CI95 [0.000, 1.000]) | insufficient_data |
| W/L/T | 1/2/0 | - |
| Mean score delta | -1.00 (CI95 [-9.00, +8.00]) | insufficient_data |
| Search conversion | 0.722 (CI95 [0.560, 0.842]) | high_confidence |
| Timeout pressure | 0.000 | - |
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
- PRIME rate (loss/win): 0.426 / 0.407
- Search conversion (loss/win): 0.750 / 0.688

#### Recommended Actions
- None

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +9.00 | +3.00 | +0.00 |
| mid | +0.00 | -8.00 | +0.00 |
| late | -1.00 | -0.50 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->search` | 15 | 0.113 | 0.037 | 0.075 | win_heavier |
| `plain->plain` | 19 | 0.037 | 0.100 | 0.062 | loss_heavier |
| `search->prime` | 13 | 0.087 | 0.037 | 0.050 | win_heavier |
| `prime->carpet` | 19 | 0.050 | 0.094 | 0.044 | loss_heavier |
| `prime->plain` | 24 | 0.075 | 0.113 | 0.038 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 51.0 | 50.5 | 51.5 |
| <= -10 | 0.50 | 76.0 | 76.0 | 76.0 |
| <= -15 | 0.00 | 0.0 | 0.0 | 0.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 14.00, median 13.00.
- Drawdown span: mean 41.00 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 8.33 | 0.103 | 0.667 | 1.000 | 4.00 |
| <= -10 | 1.00 | 0.012 | 0.333 | 1.000 | 3.00 |
| <= -15 | 0.00 | 0.000 | 0.000 | 0.000 | 0.00 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | -0.075 | [-0.201, +0.051] | insufficient_data |
| `prime_rate_delta` | -0.019 | [-0.037, +0.000] | insufficient_data |
| `search_rate_delta` | +0.074 | [+0.062, +0.086] | insufficient_data |
| `carpet_rate_delta` | +0.006 | [+0.000, +0.012] | insufficient_data |
| `plain_rate_delta` | -0.062 | [-0.086, -0.037] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match - 2026-04-19T210056.221`: t24:-4.0/search/early, t32:-4.0/search/mid, t36:-4.0/search/mid
- `match - 2026-04-19T210146.614`: t6:-4.0/carpet/early, t28:-4.0/search/mid, t42:-4.0/search/mid
- `match - 2026-04-19T210312.247`: t10:-4.0/carpet/early, t24:-4.0/carpet/early, t30:-4.0/search/mid

### segment:opponent_archetype=prime_heavy,map_seed=map:f6a92a2b,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.333 (CI95 [0.000, 1.000]) | insufficient_data |
| W/L/T | 1/2/0 | - |
| Mean score delta | -3.00 (CI95 [-12.00, +4.00]) | insufficient_data |
| Search conversion | 0.679 (CI95 [0.493, 0.821]) | high_confidence |
| Timeout pressure | 0.000 | - |
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
- PRIME rate (loss/win): 0.407 / 0.383
- Search conversion (loss/win): 0.750 / 0.583

#### Recommended Actions
- None

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +8.00 | -2.00 | +0.00 |
| mid | -3.00 | -4.00 | +0.00 |
| late | -1.00 | -0.50 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `carpet->carpet` | 5 | 0.062 | 0.000 | 0.062 | win_heavier |
| `carpet->prime` | 19 | 0.037 | 0.100 | 0.062 | loss_heavier |
| `plain->plain` | 17 | 0.037 | 0.087 | 0.050 | loss_heavier |
| `plain->carpet` | 16 | 0.037 | 0.081 | 0.044 | loss_heavier |
| `plain->search` | 10 | 0.062 | 0.031 | 0.031 | win_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 28.5 | 23.8 | 33.2 |
| <= -10 | 0.50 | 48.0 | 48.0 | 48.0 |
| <= -15 | 0.50 | 70.0 | 70.0 | 70.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 13.67, median 11.00.
- Drawdown span: mean 37.67 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 23.00 | 0.284 | 0.667 | 1.000 | 3.50 |
| <= -10 | 7.67 | 0.095 | 0.333 | 1.000 | 7.00 |
| <= -15 | 1.00 | 0.012 | 0.333 | 1.000 | 3.00 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | -0.167 | [-0.292, -0.042] | insufficient_data |
| `prime_rate_delta` | -0.025 | [-0.037, -0.012] | insufficient_data |
| `search_rate_delta` | +0.049 | [+0.049, +0.049] | insufficient_data |
| `carpet_rate_delta` | +0.006 | [+0.000, +0.012] | insufficient_data |
| `plain_rate_delta` | -0.031 | [-0.049, -0.012] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match - 2026-04-19T210110.980`: t28:-4.0/search/mid, t32:-4.0/search/mid, t50:-4.0/search/mid
- `match - 2026-04-19T210200.747`: t30:-6.0/carpet/mid, t14:-4.0/carpet/early, t18:-4.0/search/early
- `match - 2026-04-19T210429.528`: t36:-4.0/carpet/mid, t38:-4.0/carpet/mid, t40:-4.0/search/mid
