# Batch Match Insights

## Run Overview

- Matches analyzed: **91**
- Minimum sample threshold (`n_min`): **8**
- Deficit thresholds: `-5, -10, -15`

## Prioritized Findings

> Evidence-backed tuning leads from `folder:yolanda_prime_v1_2`.

1. Negative score delta is persistent; prioritize policy weight retuning and deeper lookahead checks.
2. Catastrophic loss rate is high; add guardrail heuristics for losing states.
3. Search conversion is materially worse in losses; tighten belief threshold for SEARCH and raise fallback value floor before committing.

## Cohort Snapshot


| Cohort                      | Type   | N   | Win Rate (CI95)      | Mean Delta (CI95)      | Search Conv (CI95)   | Timeout | Catastrophic |
| --------------------------- | ------ | --- | -------------------- | ---------------------- | -------------------- | ------- | ------------ |
| `folder:yolanda_prime_v1_2` | global | 91  | 0.242 [0.154, 0.319] | -10.08 [-13.55, -7.32] | 0.531 [0.502, 0.560] | 0.000   | 0.352        |


## Cohort Details

### folder:yolanda_prime_v1_2

#### Data


| Metric            | Value                                     | Confidence      |
| ----------------- | ----------------------------------------- | --------------- |
| Win rate          | 0.242 (CI95 [0.154, 0.319])               | high_confidence |
| W/L/T             | 22/69/0                                   | -               |
| Mean score delta  | -10.08 (CI95 [-13.55, -7.32])             | high_confidence |
| Search conversion | 0.531 (CI95 [0.502, 0.560])               | high_confidence |
| Timeout pressure  | 0.000                                     | -               |
| Catastrophic loss | 0.352 (`final score delta <= -15 points`) | -               |


#### Definitions

- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation

- Persistent underperformance signal: CI95 for mean score delta remains below zero.
- Elevated catastrophic loss risk; prioritize guardrails in losing trajectories.

#### Loss Drivers

- PRIME rate (loss/win): 0.411 / 0.406
- Search conversion (loss/win): 0.514 / 0.596

#### Recommended Actions

1. Negative score delta is persistent; prioritize policy weight retuning and deeper lookahead checks.
2. Catastrophic loss rate is high; add guardrail heuristics for losing states.
3. Search conversion is materially worse in losses; tighten belief threshold for SEARCH and raise fallback value floor before committing.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.


| Phase | Wins  | Losses | Ties  |
| ----- | ----- | ------ | ----- |
| early | +2.86 | -1.67  | +0.00 |
| mid   | +6.36 | -5.94  | +0.00 |
| late  | +0.23 | -8.70  | +0.00 |


#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.


| Transition      | Support | Win rate | Loss rate | Gap   | Bias         |
| --------------- | ------- | -------- | --------- | ----- | ------------ |
| `search->prime` | 443     | 0.048    | 0.065     | 0.017 | loss_heavier |
| `carpet->prime` | 381     | 0.064    | 0.049     | 0.016 | win_heavier  |
| `prime->plain`  | 721     | 0.110    | 0.096     | 0.014 | win_heavier  |
| `plain->plain`  | 690     | 0.105    | 0.091     | 0.014 | win_heavier  |
| `plain->carpet` | 316     | 0.052    | 0.041     | 0.011 | win_heavier  |


#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.


| Threshold | Onset rate | Median turn | Q1   | Q3   |
| --------- | ---------- | ----------- | ---- | ---- |
| <= -5     | 1.00       | 26.0        | 15.0 | 44.0 |
| <= -10    | 0.74       | 44.0        | 31.0 | 58.0 |
| <= -15    | 0.55       | 46.5        | 41.2 | 57.8 |


#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.
- Max drawdown: mean 21.57, median 19.00.
- Drawdown span: mean 40.92 turns.


| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
| --------- | ---------------------------- | --------------------- | ---------- | ------------------------- | --------------------- |
| <= -5     | 26.66                        | 0.329                 | 0.857      | 0.821                     | 10.91                 |
| <= -10    | 15.67                        | 0.193                 | 0.582      | 0.679                     | 12.15                 |
| <= -15    | 9.35                         | 0.115                 | 0.418      | 0.605                     | 13.26                 |


#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.


| Metric                    | Delta  | CI95             | Confidence        |
| ------------------------- | ------ | ---------------- | ----------------- |
| `search_conversion_delta` | +0.102 | [+0.008, +0.195] | high_confidence   |
| `prime_rate_delta`        | -0.005 | [-0.022, +0.011] | medium_confidence |
| `search_rate_delta`       | -0.026 | [-0.044, -0.008] | high_confidence   |
| `carpet_rate_delta`       | +0.006 | [-0.002, +0.014] | medium_confidence |
| `plain_rate_delta`        | +0.025 | [-0.000, +0.046] | medium_confidence |


#### Diagnostics: Top Turning Points (per match)

- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (10)`: t12:-6.0/carpet/early, t72:-4.0/carpet/late, t78:-4.0/search/late
- `match (11)`: t12:-6.0/carpet/early, t28:-4.0/search/mid, t36:-4.0/carpet/mid
- `match (12)`: t54:-4.0/carpet/late, t56:-4.0/carpet/late, t58:-4.0/search/late
- `match (13)`: t12:-10.0/carpet/early, t28:-6.0/carpet/mid, t30:-4.0/search/mid
- `match (14)`: t12:-10.0/carpet/early, t26:-10.0/carpet/early, t36:-4.0/carpet/mid
- `match (15)`: t14:-10.0/carpet/early, t4:-4.0/search/early, t40:-4.0/carpet/mid
- `match (16)`: t24:-10.0/carpet/early, t36:-4.0/carpet/mid, t62:-4.0/carpet/late
- `match (17)`: t4:-4.0/carpet/early, t38:-4.0/search/mid, t44:-4.0/carpet/mid

## Stratified Cohort Insights and Analytics

- Segment-level insights are grouped here to keep global findings focused and comparable.


| Cohort                                                                                    | N   | Win Rate (CI95)      | Mean Delta (CI95)      | Search Conv (CI95)   |
| ----------------------------------------------------------------------------------------- | --- | -------------------- | ---------------------- | -------------------- |
| `segment:opponent_archetype=other,map_seed=other,opening_family=other`                    | 66  | 0.288 [0.182, 0.394] | -9.73 [-13.53, -5.98]  | 0.545 [0.510, 0.580] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:3d17ebed,opening_family=prime_chain` | 4   | 0.500 [0.000, 1.000] | +1.75 [-16.00, +19.50] | 0.421 [0.302, 0.550] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:34f8da3b,opening_family=prime_chain` | 3   | 0.000 [0.000, 0.000] | -9.00 [-18.00, -1.00]  | 0.500 [0.358, 0.642] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:2e61c70c,opening_family=prime_chain` | 3   | 0.000 [0.000, 0.000] | -8.67 [-9.00, -8.00]   | 0.676 [0.508, 0.809] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:293e22a8,opening_family=prime_chain` | 3   | 0.333 [0.000, 1.000] | -14.33 [-24.00, +5.00] | 0.417 [0.288, 0.557] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:78cbca98,opening_family=prime_chain` | 3   | 0.000 [0.000, 0.000] | -10.33 [-12.00, -9.00] | 0.421 [0.279, 0.578] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:32c003b7,opening_family=prime_chain` | 3   | 0.000 [0.000, 0.000] | -15.67 [-27.00, -5.00] | 0.639 [0.476, 0.775] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:d256afbc,opening_family=prime_chain` | 3   | 0.000 [0.000, 0.000] | -15.67 [-23.00, -9.00] | 0.528 [0.370, 0.680] |


### segment:opponent_archetype=other,map_seed=other,opening_family=other

#### Data


| Metric            | Value                                     | Confidence      |
| ----------------- | ----------------------------------------- | --------------- |
| Win rate          | 0.288 (CI95 [0.182, 0.394])               | high_confidence |
| W/L/T             | 19/47/0                                   | -               |
| Mean score delta  | -9.73 (CI95 [-13.53, -5.98])              | high_confidence |
| Search conversion | 0.545 (CI95 [0.510, 0.580])               | high_confidence |
| Timeout pressure  | 0.000                                     | -               |
| Catastrophic loss | 0.333 (`final score delta <= -15 points`) | -               |


#### Definitions

- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation

- Persistent underperformance signal: CI95 for mean score delta remains below zero.
- Elevated catastrophic loss risk; prioritize guardrails in losing trajectories.

#### Loss Drivers

- PRIME rate (loss/win): 0.417 / 0.408
- Search conversion (loss/win): 0.513 / 0.642

#### Recommended Actions

1. Negative score delta is persistent; prioritize policy weight retuning and deeper lookahead checks.
2. Catastrophic loss rate is high; add guardrail heuristics for losing states.
3. Search conversion is materially worse in losses; tighten belief threshold for SEARCH and raise fallback value floor before committing.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.


| Phase | Wins  | Losses | Ties  |
| ----- | ----- | ------ | ----- |
| early | +3.00 | -1.98  | +0.00 |
| mid   | +5.21 | -6.21  | +0.00 |
| late  | +0.42 | -8.96  | +0.00 |


#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.


| Transition      | Support | Win rate | Loss rate | Gap   | Bias         |
| --------------- | ------- | -------- | --------- | ----- | ------------ |
| `prime->plain`  | 546     | 0.116    | 0.098     | 0.018 | win_heavier  |
| `search->prime` | 328     | 0.049    | 0.067     | 0.018 | loss_heavier |
| `carpet->prime` | 289     | 0.067    | 0.050     | 0.017 | win_heavier  |
| `prime->prime`  | 1001    | 0.178    | 0.194     | 0.016 | loss_heavier |
| `plain->carpet` | 239     | 0.055    | 0.041     | 0.013 | win_heavier  |


#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.


| Threshold | Onset rate | Median turn | Q1   | Q3   |
| --------- | ---------- | ----------- | ---- | ---- |
| <= -5     | 1.00       | 23.0        | 14.5 | 38.0 |
| <= -10    | 0.74       | 43.0        | 30.0 | 51.5 |
| <= -15    | 0.57       | 44.0        | 39.5 | 55.5 |


#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.
- Max drawdown: mean 21.42, median 18.50.
- Drawdown span: mean 39.47 turns.


| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
| --------- | ---------------------------- | --------------------- | ---------- | ------------------------- | --------------------- |
| <= -5     | 25.85                        | 0.319                 | 0.818      | 0.870                     | 8.96                  |
| <= -10    | 15.02                        | 0.185                 | 0.561      | 0.703                     | 11.78                 |
| <= -15    | 9.74                         | 0.120                 | 0.409      | 0.556                     | 14.70                 |


#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.


| Metric                    | Delta  | CI95             | Confidence        |
| ------------------------- | ------ | ---------------- | ----------------- |
| `search_conversion_delta` | +0.132 | [+0.052, +0.216] | high_confidence   |
| `prime_rate_delta`        | -0.009 | [-0.028, +0.010] | medium_confidence |
| `search_rate_delta`       | -0.028 | [-0.045, -0.011] | high_confidence   |
| `carpet_rate_delta`       | +0.008 | [-0.001, +0.017] | medium_confidence |
| `plain_rate_delta`        | +0.029 | [+0.001, +0.055] | high_confidence   |


#### Diagnostics: Top Turning Points (per match)

- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (10)`: t12:-6.0/carpet/early, t72:-4.0/carpet/late, t78:-4.0/search/late
- `match (11)`: t12:-6.0/carpet/early, t28:-4.0/search/mid, t36:-4.0/carpet/mid
- `match (12)`: t54:-4.0/carpet/late, t56:-4.0/carpet/late, t58:-4.0/search/late
- `match (13)`: t12:-10.0/carpet/early, t28:-6.0/carpet/mid, t30:-4.0/search/mid
- `match (74)`: t16:-6.0/carpet/early, t42:-6.0/carpet/mid, t38:-4.0/carpet/mid
- `match (14)`: t12:-10.0/carpet/early, t26:-10.0/carpet/early, t36:-4.0/carpet/mid
- `match (15)`: t14:-10.0/carpet/early, t4:-4.0/search/early, t40:-4.0/carpet/mid
- `match (16)`: t24:-10.0/carpet/early, t36:-4.0/carpet/mid, t62:-4.0/carpet/late

### segment:opponent_archetype=prime_heavy,map_seed=map:3d17ebed,opening_family=prime_chain

#### Data


| Metric            | Value                                     | Confidence        |
| ----------------- | ----------------------------------------- | ----------------- |
| Win rate          | 0.500 (CI95 [0.000, 1.000])               | insufficient_data |
| W/L/T             | 2/2/0                                     | -                 |
| Mean score delta  | +1.75 (CI95 [-16.00, +19.50])             | insufficient_data |
| Search conversion | 0.421 (CI95 [0.302, 0.550])               | high_confidence   |
| Timeout pressure  | 0.000                                     | -                 |
| Catastrophic loss | 0.250 (`final score delta <= -15 points`) | -                 |


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

- PRIME rate (loss/win): 0.377 / 0.401
- Search conversion (loss/win): 0.560 / 0.312

#### Recommended Actions

- None

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.


| Phase | Wins   | Losses | Ties  |
| ----- | ------ | ------ | ----- |
| early | +1.00  | +4.00  | +0.00 |
| mid   | +20.50 | -7.00  | +0.00 |
| late  | -2.00  | -13.00 | +0.00 |


#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.


| Transition      | Support | Win rate | Loss rate | Gap   | Bias         |
| --------------- | ------- | -------- | --------- | ----- | ------------ |
| `prime->prime`  | 54      | 0.194    | 0.144     | 0.050 | win_heavier  |
| `prime->search` | 19      | 0.081    | 0.037     | 0.044 | win_heavier  |
| `prime->plain`  | 31      | 0.075    | 0.119     | 0.044 | loss_heavier |
| `prime->carpet` | 21      | 0.050    | 0.081     | 0.031 | loss_heavier |
| `plain->carpet` | 12      | 0.025    | 0.050     | 0.025 | loss_heavier |


#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.


| Threshold | Onset rate | Median turn | Q1   | Q3   |
| --------- | ---------- | ----------- | ---- | ---- |
| <= -5     | 1.00       | 38.5        | 34.2 | 42.8 |
| <= -10    | 1.00       | 61.0        | 54.5 | 67.5 |
| <= -15    | 0.50       | 76.0        | 76.0 | 76.0 |


#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.
- Max drawdown: mean 18.25, median 16.00.
- Drawdown span: mean 38.00 turns.


| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
| --------- | ---------------------------- | --------------------- | ---------- | ------------------------- | --------------------- |
| <= -5     | 15.75                        | 0.194                 | 1.000      | 1.000                     | 2.25                  |
| <= -10    | 5.25                         | 0.065                 | 0.500      | 0.500                     | 3.50                  |
| <= -15    | 1.25                         | 0.015                 | 0.250      | 0.000                     | 4.00                  |


#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.


| Metric                    | Delta  | CI95             | Confidence        |
| ------------------------- | ------ | ---------------- | ----------------- |
| `search_conversion_delta` | -0.194 | [-0.389, +0.000] | insufficient_data |
| `prime_rate_delta`        | +0.025 | [-0.012, +0.062] | insufficient_data |
| `search_rate_delta`       | +0.043 | [-0.049, +0.136] | insufficient_data |
| `carpet_rate_delta`       | -0.043 | [-0.062, -0.025] | insufficient_data |
| `plain_rate_delta`        | -0.025 | [-0.074, +0.025] | insufficient_data |


#### Diagnostics: Top Turning Points (per match)

- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (47)`: t10:-4.0/carpet/early, t48:-4.0/carpet/mid, t66:-4.0/carpet/late
- `match (66)`: t10:-6.0/carpet/early, t70:-4.0/search/late, t28:-2.0/carpet/mid
- `match (7)`: t30:-4.0/search/mid, t44:-4.0/search/mid, t46:-4.0/search/mid
- `match (76)`: t24:-10.0/carpet/early, t32:-4.0/search/mid, t56:-4.0/carpet/late

### segment:opponent_archetype=prime_heavy,map_seed=map:34f8da3b,opening_family=prime_chain

#### Data


| Metric            | Value                                     | Confidence        |
| ----------------- | ----------------------------------------- | ----------------- |
| Win rate          | 0.000 (CI95 [0.000, 0.000])               | insufficient_data |
| W/L/T             | 0/3/0                                     | -                 |
| Mean score delta  | -9.00 (CI95 [-18.00, -1.00])              | insufficient_data |
| Search conversion | 0.500 (CI95 [0.358, 0.642])               | high_confidence   |
| Timeout pressure  | 0.000                                     | -                 |
| Catastrophic loss | 0.333 (`final score delta <= -15 points`) | -                 |


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

- PRIME rate (loss/win): 0.391 / 0.000
- Search conversion (loss/win): 0.500 / 0.000

#### Recommended Actions

1. Losses over-index on PRIME turns; reduce over-priming in trailing states and shift budget to SEARCH/CARPET opportunities.
2. Early phase collapses in losses (mean delta change -2.67); tighten opening move safety and reduce high-variance branches in first third.
3. Transition `prime->prime` is loss-heavier (gap 0.217); revisit policy thresholds governing this move switch.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.


| Phase | Wins  | Losses | Ties  |
| ----- | ----- | ------ | ----- |
| early | +0.00 | -2.67  | +0.00 |
| mid   | +0.00 | -4.33  | +0.00 |
| late  | +0.00 | -2.00  | +0.00 |


#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.


| Transition      | Support | Win rate | Loss rate | Gap   | Bias         |
| --------------- | ------- | -------- | --------- | ----- | ------------ |
| `prime->prime`  | 52      | 0.000    | 0.217     | 0.217 | loss_heavier |
| `plain->plain`  | 23      | 0.000    | 0.096     | 0.096 | loss_heavier |
| `plain->prime`  | 22      | 0.000    | 0.092     | 0.092 | loss_heavier |
| `search->plain` | 20      | 0.000    | 0.083     | 0.083 | loss_heavier |
| `prime->plain`  | 19      | 0.000    | 0.079     | 0.079 | loss_heavier |


#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.


| Threshold | Onset rate | Median turn | Q1   | Q3   |
| --------- | ---------- | ----------- | ---- | ---- |
| <= -5     | 1.00       | 36.0        | 28.0 | 40.0 |
| <= -10    | 0.33       | 38.0        | 38.0 | 38.0 |
| <= -15    | 0.33       | 49.0        | 49.0 | 49.0 |


#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.
- Max drawdown: mean 17.67, median 18.00.
- Drawdown span: mean 47.67 turns.


| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
| --------- | ---------------------------- | --------------------- | ---------- | ------------------------- | --------------------- |
| <= -5     | 26.00                        | 0.321                 | 1.000      | 0.667                     | 22.00                 |
| <= -10    | 14.00                        | 0.173                 | 0.333      | 1.000                     | 1.00                  |
| <= -15    | 5.67                         | 0.070                 | 0.333      | 1.000                     | 14.00                 |


#### Diagnostics: Top Turning Points (per match)

- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (17)`: t4:-4.0/carpet/early, t38:-4.0/search/mid, t44:-4.0/carpet/mid
- `match (61)`: t20:-10.0/carpet/early, t24:-4.0/search/early, t40:-4.0/carpet/mid
- `match (92)`: t12:-10.0/carpet/early, t36:-6.0/carpet/mid, t26:-4.0/carpet/early

### segment:opponent_archetype=prime_heavy,map_seed=map:2e61c70c,opening_family=prime_chain

#### Data


| Metric            | Value                                     | Confidence        |
| ----------------- | ----------------------------------------- | ----------------- |
| Win rate          | 0.000 (CI95 [0.000, 0.000])               | insufficient_data |
| W/L/T             | 0/3/0                                     | -                 |
| Mean score delta  | -8.67 (CI95 [-9.00, -8.00])               | insufficient_data |
| Search conversion | 0.676 (CI95 [0.508, 0.809])               | high_confidence   |
| Timeout pressure  | 0.000                                     | -                 |
| Catastrophic loss | 0.000 (`final score delta <= -15 points`) | -                 |


#### Definitions

- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation

- Outcome direction is less stable; gather more matches before strong conclusions.

#### Loss Drivers

- PRIME rate (loss/win): 0.465 / 0.000
- Search conversion (loss/win): 0.676 / 0.000

#### Recommended Actions

1. Losses over-index on PRIME turns; reduce over-priming in trailing states and shift budget to SEARCH/CARPET opportunities.
2. Transition `prime->prime` is loss-heavier (gap 0.271); revisit policy thresholds governing this move switch.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.


| Phase | Wins  | Losses | Ties  |
| ----- | ----- | ------ | ----- |
| early | +0.00 | +7.33  | +0.00 |
| mid   | +0.00 | -4.67  | +0.00 |
| late  | +0.00 | -11.33 | +0.00 |


#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.


| Transition      | Support | Win rate | Loss rate | Gap   | Bias         |
| --------------- | ------- | -------- | --------- | ----- | ------------ |
| `prime->prime`  | 65      | 0.000    | 0.271     | 0.271 | loss_heavier |
| `plain->prime`  | 26      | 0.000    | 0.108     | 0.108 | loss_heavier |
| `plain->plain`  | 23      | 0.000    | 0.096     | 0.096 | loss_heavier |
| `search->plain` | 17      | 0.000    | 0.071     | 0.071 | loss_heavier |
| `prime->carpet` | 17      | 0.000    | 0.071     | 0.071 | loss_heavier |


#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.


| Threshold | Onset rate | Median turn | Q1   | Q3   |
| --------- | ---------- | ----------- | ---- | ---- |
| <= -5     | 1.00       | 62.0        | 60.0 | 62.0 |
| <= -10    | 0.00       | 0.0         | 0.0  | 0.0  |
| <= -15    | 0.00       | 0.0         | 0.0  | 0.0  |


#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.
- Max drawdown: mean 22.00, median 25.00.
- Drawdown span: mean 49.00 turns.


| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
| --------- | ---------------------------- | --------------------- | ---------- | ------------------------- | --------------------- |
| <= -5     | 10.33                        | 0.128                 | 1.000      | 1.000                     | 2.67                  |
| <= -10    | 0.00                         | 0.000                 | 0.000      | 0.000                     | 0.00                  |
| <= -15    | 0.00                         | 0.000                 | 0.000      | 0.000                     | 0.00                  |


#### Diagnostics: Top Turning Points (per match)

- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (22)`: t28:-10.0/carpet/mid, t8:-4.0/carpet/early, t46:-4.0/search/mid
- `match (35)`: t12:-10.0/carpet/early, t36:-10.0/carpet/mid, t42:-4.0/search/mid
- `match (36)`: t12:-10.0/carpet/early, t36:-10.0/carpet/mid, t42:-4.0/search/mid

### segment:opponent_archetype=prime_heavy,map_seed=map:293e22a8,opening_family=prime_chain

#### Data


| Metric            | Value                                     | Confidence        |
| ----------------- | ----------------------------------------- | ----------------- |
| Win rate          | 0.333 (CI95 [0.000, 1.000])               | insufficient_data |
| W/L/T             | 1/2/0                                     | -                 |
| Mean score delta  | -14.33 (CI95 [-24.00, +5.00])             | insufficient_data |
| Search conversion | 0.417 (CI95 [0.288, 0.557])               | high_confidence   |
| Timeout pressure  | 0.000                                     | -                 |
| Catastrophic loss | 0.667 (`final score delta <= -15 points`) | -                 |


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

- PRIME rate (loss/win): 0.395 / 0.370
- Search conversion (loss/win): 0.368 / 0.600

#### Recommended Actions

1. Search conversion is materially worse in losses; tighten belief threshold for SEARCH and raise fallback value floor before committing.
2. Early phase collapses in losses (mean delta change -4.00); tighten opening move safety and reduce high-variance branches in first third.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.


| Phase | Wins  | Losses | Ties  |
| ----- | ----- | ------ | ----- |
| early | +4.00 | -4.00  | +0.00 |
| mid   | +0.00 | -2.00  | +0.00 |
| late  | +1.00 | -18.00 | +0.00 |


#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.


| Transition      | Support | Win rate | Loss rate | Gap   | Bias         |
| --------------- | ------- | -------- | --------- | ----- | ------------ |
| `plain->plain`  | 20      | 0.175    | 0.037     | 0.137 | win_heavier  |
| `search->prime` | 22      | 0.025    | 0.125     | 0.100 | loss_heavier |
| `prime->prime`  | 42      | 0.225    | 0.150     | 0.075 | win_heavier  |
| `prime->search` | 24      | 0.050    | 0.125     | 0.075 | loss_heavier |
| `plain->prime`  | 21      | 0.113    | 0.075     | 0.038 | win_heavier  |


#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.


| Threshold | Onset rate | Median turn | Q1   | Q3   |
| --------- | ---------- | ----------- | ---- | ---- |
| <= -5     | 1.00       | 10.0        | 10.0 | 10.0 |
| <= -10    | 1.00       | 58.0        | 58.0 | 58.0 |
| <= -15    | 1.00       | 58.0        | 58.0 | 58.0 |


#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.
- Max drawdown: mean 22.67, median 27.00.
- Drawdown span: mean 49.00 turns.


| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
| --------- | ---------------------------- | --------------------- | ---------- | ------------------------- | --------------------- |
| <= -5     | 22.67                        | 0.280                 | 0.667      | 1.000                     | 6.00                  |
| <= -10    | 15.33                        | 0.189                 | 0.667      | 0.000                     | 22.00                 |
| <= -15    | 8.00                         | 0.099                 | 0.667      | 1.000                     | 1.00                  |


#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.


| Metric                    | Delta  | CI95             | Confidence        |
| ------------------------- | ------ | ---------------- | ----------------- |
| `search_conversion_delta` | +0.232 | [+0.232, +0.232] | insufficient_data |
| `prime_rate_delta`        | -0.025 | [-0.025, -0.025] | insufficient_data |
| `search_rate_delta`       | -0.111 | [-0.111, -0.111] | insufficient_data |
| `carpet_rate_delta`       | -0.025 | [-0.025, -0.025] | insufficient_data |
| `plain_rate_delta`        | +0.160 | [+0.160, +0.160] | insufficient_data |


#### Diagnostics: Top Turning Points (per match)

- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (23)`: t12:-10.0/carpet/early, t42:-4.0/carpet/mid, t48:-4.0/search/mid
- `match (80)`: t58:-10.0/carpet/late, t10:-4.0/search/early, t26:-4.0/search/early
- `match (81)`: t58:-10.0/carpet/late, t10:-4.0/search/early, t26:-4.0/search/early

### segment:opponent_archetype=prime_heavy,map_seed=map:78cbca98,opening_family=prime_chain

#### Data


| Metric            | Value                                     | Confidence        |
| ----------------- | ----------------------------------------- | ----------------- |
| Win rate          | 0.000 (CI95 [0.000, 0.000])               | insufficient_data |
| W/L/T             | 0/3/0                                     | -                 |
| Mean score delta  | -10.33 (CI95 [-12.00, -9.00])             | insufficient_data |
| Search conversion | 0.421 (CI95 [0.279, 0.578])               | high_confidence   |
| Timeout pressure  | 0.000                                     | -                 |
| Catastrophic loss | 0.000 (`final score delta <= -15 points`) | -                 |


#### Definitions

- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation

- Outcome direction is less stable; gather more matches before strong conclusions.

#### Loss Drivers

- PRIME rate (loss/win): 0.383 / 0.000
- Search conversion (loss/win): 0.421 / 0.000

#### Recommended Actions

1. Losses over-index on PRIME turns; reduce over-priming in trailing states and shift budget to SEARCH/CARPET opportunities.
2. Early phase collapses in losses (mean delta change -5.33); tighten opening move safety and reduce high-variance branches in first third.
3. Transition `prime->prime` is loss-heavier (gap 0.183); revisit policy thresholds governing this move switch.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.


| Phase | Wins  | Losses | Ties  |
| ----- | ----- | ------ | ----- |
| early | +0.00 | -5.33  | +0.00 |
| mid   | +0.00 | -4.67  | +0.00 |
| late  | +0.00 | -0.33  | +0.00 |


#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.


| Transition      | Support | Win rate | Loss rate | Gap   | Bias         |
| --------------- | ------- | -------- | --------- | ----- | ------------ |
| `prime->prime`  | 44      | 0.000    | 0.183     | 0.183 | loss_heavier |
| `plain->prime`  | 30      | 0.000    | 0.125     | 0.125 | loss_heavier |
| `plain->plain`  | 25      | 0.000    | 0.104     | 0.104 | loss_heavier |
| `prime->plain`  | 21      | 0.000    | 0.087     | 0.087 | loss_heavier |
| `search->plain` | 16      | 0.000    | 0.067     | 0.067 | loss_heavier |


#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.


| Threshold | Onset rate | Median turn | Q1   | Q3   |
| --------- | ---------- | ----------- | ---- | ---- |
| <= -5     | 1.00       | 22.0        | 20.5 | 24.0 |
| <= -10    | 1.00       | 34.0        | 33.0 | 46.5 |
| <= -15    | 0.33       | 46.0        | 46.0 | 46.0 |


#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.
- Max drawdown: mean 21.00, median 19.00.
- Drawdown span: mean 31.33 turns.


| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
| --------- | ---------------------------- | --------------------- | ---------- | ------------------------- | --------------------- |
| <= -5     | 48.33                        | 0.597                 | 1.000      | 0.667                     | 30.00                 |
| <= -10    | 21.00                        | 0.259                 | 1.000      | 1.000                     | 5.00                  |
| <= -15    | 5.00                         | 0.062                 | 0.333      | 1.000                     | 15.00                 |


#### Diagnostics: Top Turning Points (per match)

- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (32)`: t10:-6.0/carpet/early, t22:-4.0/search/early, t32:-4.0/search/mid
- `match (45)`: t18:-4.0/carpet/early, t26:-4.0/search/early, t34:-4.0/carpet/mid
- `match (78)`: t34:-10.0/carpet/mid, t62:-6.0/carpet/late, t32:-4.0/search/mid

### segment:opponent_archetype=prime_heavy,map_seed=map:32c003b7,opening_family=prime_chain

#### Data


| Metric            | Value                                     | Confidence        |
| ----------------- | ----------------------------------------- | ----------------- |
| Win rate          | 0.000 (CI95 [0.000, 0.000])               | insufficient_data |
| W/L/T             | 0/3/0                                     | -                 |
| Mean score delta  | -15.67 (CI95 [-27.00, -5.00])             | insufficient_data |
| Search conversion | 0.639 (CI95 [0.476, 0.775])               | high_confidence   |
| Timeout pressure  | 0.000                                     | -                 |
| Catastrophic loss | 0.667 (`final score delta <= -15 points`) | -                 |


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

- PRIME rate (loss/win): 0.399 / 0.000
- Search conversion (loss/win): 0.639 / 0.000

#### Recommended Actions

1. Losses over-index on PRIME turns; reduce over-priming in trailing states and shift budget to SEARCH/CARPET opportunities.
2. Transition `prime->prime` is loss-heavier (gap 0.212); revisit policy thresholds governing this move switch.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.


| Phase | Wins  | Losses | Ties  |
| ----- | ----- | ------ | ----- |
| early | +0.00 | -0.33  | +0.00 |
| mid   | +0.00 | -8.67  | +0.00 |
| late  | +0.00 | -6.67  | +0.00 |


#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.


| Transition      | Support | Win rate | Loss rate | Gap   | Bias         |
| --------------- | ------- | -------- | --------- | ----- | ------------ |
| `prime->prime`  | 51      | 0.000    | 0.212     | 0.212 | loss_heavier |
| `plain->prime`  | 29      | 0.000    | 0.121     | 0.121 | loss_heavier |
| `plain->plain`  | 28      | 0.000    | 0.117     | 0.117 | loss_heavier |
| `prime->plain`  | 19      | 0.000    | 0.079     | 0.079 | loss_heavier |
| `search->plain` | 18      | 0.000    | 0.075     | 0.075 | loss_heavier |


#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.


| Threshold | Onset rate | Median turn | Q1   | Q3   |
| --------- | ---------- | ----------- | ---- | ---- |
| <= -5     | 1.00       | 44.0        | 28.0 | 45.0 |
| <= -10    | 1.00       | 49.0        | 33.0 | 58.5 |
| <= -15    | 0.67       | 42.0        | 35.0 | 49.0 |


#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.
- Max drawdown: mean 24.00, median 23.00.
- Drawdown span: mean 54.33 turns.


| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
| --------- | ---------------------------- | --------------------- | ---------- | ------------------------- | --------------------- |
| <= -5     | 40.33                        | 0.498                 | 1.000      | 0.667                     | 12.67                 |
| <= -10    | 31.67                        | 0.391                 | 1.000      | 1.000                     | 8.67                  |
| <= -15    | 15.00                        | 0.185                 | 0.667      | 1.000                     | 10.00                 |


#### Diagnostics: Top Turning Points (per match)

- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (33)`: t28:-15.0/carpet/mid, t4:-4.0/search/early, t12:-4.0/carpet/early
- `match (73)`: t30:-6.0/carpet/mid, t46:-4.0/carpet/mid, t12:-2.0/carpet/early
- `match (75)`: t32:-6.0/carpet/mid, t14:-4.0/carpet/early, t18:-4.0/carpet/early

### segment:opponent_archetype=prime_heavy,map_seed=map:d256afbc,opening_family=prime_chain

#### Data


| Metric            | Value                                     | Confidence        |
| ----------------- | ----------------------------------------- | ----------------- |
| Win rate          | 0.000 (CI95 [0.000, 0.000])               | insufficient_data |
| W/L/T             | 0/3/0                                     | -                 |
| Mean score delta  | -15.67 (CI95 [-23.00, -9.00])             | insufficient_data |
| Search conversion | 0.528 (CI95 [0.370, 0.680])               | high_confidence   |
| Timeout pressure  | 0.000                                     | -                 |
| Catastrophic loss | 0.667 (`final score delta <= -15 points`) | -                 |


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

- PRIME rate (loss/win): 0.399 / 0.000
- Search conversion (loss/win): 0.528 / 0.000

#### Recommended Actions

1. Losses over-index on PRIME turns; reduce over-priming in trailing states and shift budget to SEARCH/CARPET opportunities.
2. Transition `plain->prime` is loss-heavier (gap 0.146); revisit policy thresholds governing this move switch.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.


| Phase | Wins  | Losses | Ties  |
| ----- | ----- | ------ | ----- |
| early | +0.00 | -1.00  | +0.00 |
| mid   | +0.00 | -5.67  | +0.00 |
| late  | +0.00 | -9.00  | +0.00 |


#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.


| Transition      | Support | Win rate | Loss rate | Gap   | Bias         |
| --------------- | ------- | -------- | --------- | ----- | ------------ |
| `plain->prime`  | 35      | 0.000    | 0.146     | 0.146 | loss_heavier |
| `prime->plain`  | 32      | 0.000    | 0.133     | 0.133 | loss_heavier |
| `prime->prime`  | 29      | 0.000    | 0.121     | 0.121 | loss_heavier |
| `search->prime` | 23      | 0.000    | 0.096     | 0.096 | loss_heavier |
| `plain->plain`  | 22      | 0.000    | 0.092     | 0.092 | loss_heavier |


#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.


| Threshold | Onset rate | Median turn | Q1   | Q3   |
| --------- | ---------- | ----------- | ---- | ---- |
| <= -5     | 1.00       | 57.0        | 33.5 | 61.5 |
| <= -10    | 1.00       | 61.0        | 42.5 | 68.5 |
| <= -15    | 0.67       | 54.5        | 50.2 | 58.8 |


#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.
- Max drawdown: mean 23.33, median 24.00.
- Drawdown span: mean 38.67 turns.


| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
| --------- | ---------------------------- | --------------------- | ---------- | ------------------------- | --------------------- |
| <= -5     | 34.33                        | 0.424                 | 1.000      | 0.333                     | 12.67                 |
| <= -10    | 25.33                        | 0.313                 | 1.000      | 0.667                     | 8.33                  |
| <= -15    | 12.67                        | 0.156                 | 0.667      | 0.500                     | 18.00                 |


#### Diagnostics: Top Turning Points (per match)

- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (37)`: t46:-10.0/carpet/mid, t24:-6.0/carpet/early, t10:-4.0/search/early
- `match (46)`: t14:-6.0/carpet/early, t34:-4.0/carpet/mid, t64:-4.0/carpet/late
- `match (51)`: t44:-10.0/carpet/mid, t62:-4.0/carpet/late, t7:-2.0/search/early

