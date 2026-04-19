# Batch Match Insights

## Run Overview
- Matches analyzed: **106**
- Minimum sample threshold (`n_min`): **8**
- Deficit thresholds: `-5, -10, -15`

## Prioritized Findings
> Evidence-backed tuning leads from `folder:yolanda_prime_v4_7_baseline`.
1. Early phase collapses in losses (mean delta change -2.50); tighten opening move safety and reduce high-variance branches in first third.

## Cohort Snapshot

| Cohort | Type | N | Win Rate (CI95) | Mean Delta (CI95) | Search Conv (CI95) | Timeout | Catastrophic |
|---|---|---:|---|---|---|---:|---:|
| `folder:yolanda_prime_v4_7_baseline` | global | 106 | 0.547 [0.458, 0.642] | +0.92 [-1.80, +3.40] | 0.511 [0.485, 0.536] | 0.094 | 0.113 |

## Cohort Details
### folder:yolanda_prime_v4_7_baseline

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.547 (CI95 [0.458, 0.642]) | medium_confidence |
| W/L/T | 56/46/4 | - |
| Mean score delta | +0.92 (CI95 [-1.80, +3.40]) | medium_confidence |
| Search conversion | 0.511 (CI95 [0.485, 0.536]) | high_confidence |
| Timeout pressure | 0.094 | - |
| Catastrophic loss | 0.113 (`final score delta <= -15 points`) | - |

#### Definitions
- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation
- Outcome direction is less stable; gather more matches before strong conclusions.

#### Loss Drivers
- PRIME rate (loss/win): 0.404 / 0.427
- Search conversion (loss/win): 0.494 / 0.515

#### Recommended Actions
1. Early phase collapses in losses (mean delta change -2.50); tighten opening move safety and reduce high-variance branches in first third.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +2.36 | -2.50 | +4.00 |
| mid | +5.05 | -3.17 | +3.50 |
| late | +3.46 | -5.43 | -7.50 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `plain->search` | 416 | 0.043 | 0.061 | 0.018 | loss_heavier |
| `search->plain` | 446 | 0.049 | 0.062 | 0.013 | loss_heavier |
| `search->search` | 227 | 0.022 | 0.035 | 0.012 | loss_heavier |
| `carpet->prime` | 449 | 0.060 | 0.049 | 0.012 | win_heavier |
| `prime->prime` | 1505 | 0.189 | 0.179 | 0.011 | win_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 0.96 | 23.0 | 15.5 | 38.0 |
| <= -10 | 0.80 | 40.0 | 26.0 | 61.0 |
| <= -15 | 0.46 | 57.0 | 42.0 | 68.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 15.80, median 14.00.
- Drawdown span: mean 27.15 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 16.63 | 0.205 | 0.642 | 0.897 | 10.00 |
| <= -10 | 7.66 | 0.095 | 0.387 | 0.927 | 6.17 |
| <= -15 | 2.58 | 0.032 | 0.208 | 0.727 | 7.41 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | +0.035 | [-0.024, +0.086] | medium_confidence |
| `prime_rate_delta` | +0.022 | [+0.003, +0.042] | high_confidence |
| `search_rate_delta` | -0.031 | [-0.050, -0.011] | high_confidence |
| `carpet_rate_delta` | +0.010 | [+0.003, +0.018] | high_confidence |
| `plain_rate_delta` | -0.002 | [-0.021, +0.016] | medium_confidence |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (100)`: t14:-4.0/search/early, t18:-4.0/search/early, t26:-4.0/search/early
- `match (94)`: t14:-4.0/carpet/early, t80:-4.0/search/late, t25:-2.0/search/early
- `match (95)`: t14:-4.0/carpet/early, t20:-4.0/search/early, t34:-4.0/carpet/mid
- `match (96)`: t18:-4.0/carpet/early, t24:-4.0/search/early, t58:-4.0/search/late
- `match (97)`: t14:-6.0/carpet/early, t22:-4.0/carpet/early, t42:-4.0/carpet/mid
- `match (98)`: t30:-6.0/carpet/mid, t48:-6.0/carpet/mid, t36:-4.0/search/mid
- `match (99)`: t18:-10.0/carpet/early, t54:-6.0/carpet/late, t48:-4.0/carpet/mid
- `match - 2026-04-19T024149.768`: t12:-6.0/carpet/early, t66:-4.0/search/late, t11:-2.0/search/early

## Stratified Cohort Insights and Analytics

- Segment-level insights are grouped here to keep global findings focused and comparable.

| Cohort | N | Win Rate (CI95) | Mean Delta (CI95) | Search Conv (CI95) |
|---|---:|---|---|---|
| `segment:opponent_archetype=other,map_seed=other,opening_family=other` | 74 | 0.541 [0.426, 0.642] | +0.62 [-2.76, +3.62] | 0.531 [0.500, 0.561] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:32c003b7,opening_family=prime_chain` | 6 | 0.500 [0.167, 0.833] | +2.33 [-5.83, +11.83] | 0.529 [0.424, 0.632] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:124ef1c4,opening_family=prime_chain` | 4 | 0.500 [0.000, 1.000] | +2.75 [-4.25, +13.00] | 0.566 [0.433, 0.690] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:a11aba4a,opening_family=prime_chain` | 4 | 1.000 [1.000, 1.000] | +5.25 [+1.75, +10.50] | 0.407 [0.291, 0.534] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:cb448f6d,opening_family=prime_chain` | 3 | 0.333 [0.000, 1.000] | -5.00 [-20.00, +22.00] | 0.354 [0.234, 0.496] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:82ef209f,opening_family=prime_chain` | 3 | 0.333 [0.000, 1.000] | -7.33 [-19.00, +9.00] | 0.450 [0.307, 0.602] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:7fb4f3df,opening_family=prime_chain` | 3 | 0.667 [0.000, 1.000] | +4.67 [-3.00, +12.00] | 0.500 [0.345, 0.655] |
| `segment:opponent_archetype=prime_heavy,map_seed=map:0e3899f9,opening_family=prime_chain` | 3 | 0.667 [0.000, 1.000] | +3.00 [-7.00, +11.00] | 0.512 [0.365, 0.657] |

### segment:opponent_archetype=other,map_seed=other,opening_family=other

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.541 (CI95 [0.426, 0.642]) | medium_confidence |
| W/L/T | 38/32/4 | - |
| Mean score delta | +0.62 (CI95 [-2.76, +3.62]) | medium_confidence |
| Search conversion | 0.531 (CI95 [0.500, 0.561]) | high_confidence |
| Timeout pressure | 0.122 | - |
| Catastrophic loss | 0.122 (`final score delta <= -15 points`) | - |

#### Definitions
- `Win rate`: final score outcome encoded as win=1, tie=0.5, loss=0; CI95 reflects uncertainty.
- `Mean score delta`: final `a_points - b_points`; positive means ahead, negative means behind.
- `Search conversion`: rat catches divided by search turns.
- `Timeout pressure`: fraction of matches ending with either side below 5.0 time left.
- `Catastrophic loss`: fraction of matches with final score delta `<= -15`.

#### Interpretation
- Outcome direction is less stable; gather more matches before strong conclusions.

#### Loss Drivers
- PRIME rate (loss/win): 0.405 / 0.427
- Search conversion (loss/win): 0.500 / 0.545

#### Recommended Actions
1. Early phase collapses in losses (mean delta change -3.22); tighten opening move safety and reduce high-variance branches in first third.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +2.68 | -3.22 | +4.00 |
| mid | +5.29 | -3.81 | +3.50 |
| late | +3.24 | -4.84 | -7.50 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `plain->search` | 298 | 0.044 | 0.064 | 0.020 | loss_heavier |
| `search->plain` | 322 | 0.051 | 0.066 | 0.015 | loss_heavier |
| `carpet->prime` | 304 | 0.060 | 0.048 | 0.012 | win_heavier |
| `prime->carpet` | 357 | 0.068 | 0.058 | 0.010 | win_heavier |
| `plain->prime` | 654 | 0.120 | 0.113 | 0.008 | win_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 19.0 | 14.0 | 38.0 |
| <= -10 | 0.88 | 37.0 | 25.5 | 58.8 |
| <= -15 | 0.47 | 57.0 | 41.0 | 66.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 15.97, median 14.00.
- Drawdown span: mean 28.11 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 17.27 | 0.213 | 0.649 | 0.896 | 9.96 |
| <= -10 | 8.68 | 0.107 | 0.419 | 0.935 | 7.00 |
| <= -15 | 3.12 | 0.039 | 0.216 | 0.812 | 7.75 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | +0.064 | [-0.001, +0.131] | medium_confidence |
| `prime_rate_delta` | +0.021 | [-0.001, +0.042] | medium_confidence |
| `search_rate_delta` | -0.029 | [-0.050, -0.009] | high_confidence |
| `carpet_rate_delta` | +0.008 | [-0.001, +0.016] | medium_confidence |
| `plain_rate_delta` | -0.000 | [-0.027, +0.024] | medium_confidence |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (100)`: t14:-4.0/search/early, t18:-4.0/search/early, t26:-4.0/search/early
- `match (94)`: t14:-4.0/carpet/early, t80:-4.0/search/late, t25:-2.0/search/early
- `match - 2026-04-19T030413.824`: t26:-10.0/carpet/early, t8:-4.0/search/early, t12:-4.0/carpet/early
- `match (95)`: t14:-4.0/carpet/early, t20:-4.0/search/early, t34:-4.0/carpet/mid
- `match (96)`: t18:-4.0/carpet/early, t24:-4.0/search/early, t58:-4.0/search/late
- `match - 2026-04-19T112952.733`: t12:-10.0/carpet/early, t30:-4.0/carpet/mid, t58:-4.0/carpet/late
- `match (99)`: t18:-10.0/carpet/early, t54:-6.0/carpet/late, t48:-4.0/carpet/mid
- `match - 2026-04-19T113240.096`: t34:-6.0/carpet/mid, t10:-4.0/search/early, t30:-4.0/search/mid

### segment:opponent_archetype=prime_heavy,map_seed=map:32c003b7,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.500 (CI95 [0.167, 0.833]) | insufficient_data |
| W/L/T | 3/3/0 | - |
| Mean score delta | +2.33 (CI95 [-5.83, +11.83]) | insufficient_data |
| Search conversion | 0.529 (CI95 [0.424, 0.632]) | high_confidence |
| Timeout pressure | 0.167 | - |
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
- PRIME rate (loss/win): 0.428 / 0.457
- Search conversion (loss/win): 0.543 / 0.513

#### Recommended Actions
1. Transition `plain->search` is loss-heavier (gap 0.038); revisit policy thresholds governing this move switch.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | -1.00 | +1.33 | +0.00 |
| mid | +7.33 | -1.33 | +0.00 |
| late | +5.33 | -7.00 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `plain->search` | 19 | 0.021 | 0.058 | 0.038 | loss_heavier |
| `plain->plain` | 22 | 0.062 | 0.029 | 0.033 | win_heavier |
| `search->plain` | 23 | 0.033 | 0.062 | 0.029 | loss_heavier |
| `carpet->prime` | 34 | 0.079 | 0.062 | 0.017 | win_heavier |
| `search->carpet` | 11 | 0.017 | 0.029 | 0.013 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 64.0 | 50.0 | 71.0 |
| <= -10 | 0.67 | 57.0 | 49.5 | 64.5 |
| <= -15 | 0.00 | 0.0 | 0.0 | 0.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 15.00, median 14.50.
- Drawdown span: mean 19.33 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 8.00 | 0.099 | 0.667 | 0.750 | 6.75 |
| <= -10 | 1.50 | 0.019 | 0.333 | 1.000 | 2.00 |
| <= -15 | 0.00 | 0.000 | 0.000 | 0.000 | 0.00 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | -0.035 | [-0.222, +0.114] | insufficient_data |
| `prime_rate_delta` | +0.029 | [-0.021, +0.078] | insufficient_data |
| `search_rate_delta` | -0.029 | [-0.086, +0.025] | insufficient_data |
| `carpet_rate_delta` | +0.004 | [-0.016, +0.021] | insufficient_data |
| `plain_rate_delta` | -0.004 | [-0.045, +0.049] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (97)`: t14:-6.0/carpet/early, t22:-4.0/carpet/early, t42:-4.0/carpet/mid
- `match - 2026-04-19T113031.055`: t26:-4.0/search/early, t36:-4.0/carpet/mid, t42:-4.0/carpet/mid
- `match - 2026-04-19T113138.896`: t12:-6.0/carpet/early, t42:-4.0/search/mid, t46:-4.0/search/mid
- `match - 2026-04-19T113145.150`: t48:-10.0/carpet/mid, t46:-4.0/search/mid, t62:-4.0/carpet/late
- `match - 2026-04-19T113236.848`: t10:-6.0/carpet/early, t64:-6.0/carpet/late, t22:-4.0/search/early
- `match - 2026-04-19T114701.284`: t22:-6.0/carpet/early, t10:-4.0/carpet/early, t32:-4.0/search/mid

### segment:opponent_archetype=prime_heavy,map_seed=map:124ef1c4,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.500 (CI95 [0.000, 1.000]) | insufficient_data |
| W/L/T | 2/2/0 | - |
| Mean score delta | +2.75 (CI95 [-4.25, +13.00]) | insufficient_data |
| Search conversion | 0.566 (CI95 [0.433, 0.690]) | high_confidence |
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
- PRIME rate (loss/win): 0.401 / 0.407
- Search conversion (loss/win): 0.630 / 0.500

#### Recommended Actions
- None

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +6.50 | +3.50 | +0.00 |
| mid | +2.50 | +2.00 | +0.00 |
| late | +0.50 | -9.50 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `search->search` | 13 | 0.031 | 0.050 | 0.019 | loss_heavier |
| `prime->plain` | 29 | 0.100 | 0.081 | 0.019 | win_heavier |
| `carpet->plain` | 8 | 0.019 | 0.031 | 0.013 | loss_heavier |
| `plain->prime` | 38 | 0.125 | 0.113 | 0.012 | win_heavier |
| `prime->carpet` | 24 | 0.069 | 0.081 | 0.012 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 0.50 | 70.0 | 70.0 | 70.0 |
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

- Max drawdown: mean 11.75, median 12.00.
- Drawdown span: mean 22.25 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 3.00 | 0.037 | 0.500 | 1.000 | 2.00 |
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
| `search_conversion_delta` | -0.149 | [-0.236, -0.062] | insufficient_data |
| `prime_rate_delta` | +0.006 | [-0.049, +0.062] | insufficient_data |
| `search_rate_delta` | -0.006 | [-0.074, +0.062] | insufficient_data |
| `carpet_rate_delta` | -0.012 | [-0.049, +0.025] | insufficient_data |
| `plain_rate_delta` | +0.012 | [-0.062, +0.086] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match - 2026-04-19T024153.429`: t34:-6.0/carpet/mid, t10:-4.0/carpet/early, t32:-4.0/carpet/mid
- `match - 2026-04-19T024310.585`: t26:-4.0/carpet/early, t50:-4.0/search/mid, t54:-4.0/carpet/late
- `match - 2026-04-19T032334.779`: t18:-10.0/carpet/early, t10:-4.0/search/early, t36:-4.0/search/mid
- `match - 2026-04-19T113054.836`: t16:-4.0/carpet/early, t36:-4.0/search/mid, t48:-4.0/search/mid

### segment:opponent_archetype=prime_heavy,map_seed=map:a11aba4a,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 1.000 (CI95 [1.000, 1.000]) | insufficient_data |
| W/L/T | 4/0/0 | - |
| Mean score delta | +5.25 (CI95 [+1.75, +10.50]) | insufficient_data |
| Search conversion | 0.407 (CI95 [0.291, 0.534]) | high_confidence |
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

#### Recommended Actions
- None

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +2.75 | +0.00 | +0.00 |
| mid | +2.75 | +0.00 | +0.00 |
| late | -0.25 | +0.00 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->prime` | 59 | 0.184 | 0.000 | 0.184 | win_heavier |
| `prime->plain` | 33 | 0.103 | 0.000 | 0.103 | win_heavier |
| `plain->prime` | 32 | 0.100 | 0.000 | 0.100 | win_heavier |
| `prime->search` | 27 | 0.084 | 0.000 | 0.084 | win_heavier |
| `search->prime` | 25 | 0.078 | 0.000 | 0.078 | win_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 0.00 | 0.0 | 0.0 | 0.0 |
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

- Max drawdown: mean 12.50, median 12.00.
- Drawdown span: mean 17.75 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 9.25 | 0.114 | 0.500 | 1.000 | 14.00 |
| <= -10 | 0.00 | 0.000 | 0.000 | 0.000 | 0.00 |
| <= -15 | 0.00 | 0.000 | 0.000 | 0.000 | 0.00 |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match - 2026-04-19T024201.521`: t12:-6.0/carpet/early, t15:-2.0/search/early, t23:-2.0/search/early
- `match - 2026-04-19T030437.171`: t14:-4.0/carpet/early, t36:-4.0/search/mid, t38:-4.0/carpet/mid
- `match - 2026-04-19T113135.615`: t10:-6.0/carpet/early, t18:-4.0/search/early, t26:-4.0/search/early
- `match - 2026-04-19T120243.029`: t8:-4.0/search/early, t12:-4.0/carpet/early, t18:-4.0/search/early

### segment:opponent_archetype=prime_heavy,map_seed=map:cb448f6d,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.333 (CI95 [0.000, 1.000]) | insufficient_data |
| W/L/T | 1/2/0 | - |
| Mean score delta | -5.00 (CI95 [-20.00, +22.00]) | insufficient_data |
| Search conversion | 0.354 (CI95 [0.234, 0.496]) | medium_confidence |
| Timeout pressure | 0.000 | - |
| Catastrophic loss | 0.667 (`final score delta <= -15 points`) | - |

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
- PRIME rate (loss/win): 0.414 / 0.370
- Search conversion (loss/win): 0.393 / 0.300

#### Recommended Actions
1. Transition `plain->prime` is loss-heavier (gap 0.063); revisit policy thresholds governing this move switch.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | -3.00 | +1.50 | +0.00 |
| mid | +10.00 | -8.00 | +0.00 |
| late | +15.00 | -12.00 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `plain->prime` | 28 | 0.075 | 0.138 | 0.063 | loss_heavier |
| `prime->plain` | 24 | 0.062 | 0.119 | 0.056 | loss_heavier |
| `prime->carpet` | 14 | 0.037 | 0.069 | 0.031 | loss_heavier |
| `search->plain` | 13 | 0.075 | 0.044 | 0.031 | win_heavier |
| `carpet->prime` | 13 | 0.037 | 0.062 | 0.025 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 25.5 | 23.2 | 27.8 |
| <= -10 | 1.00 | 57.5 | 49.8 | 65.2 |
| <= -15 | 1.00 | 72.0 | 69.0 | 75.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 19.33, median 23.00.
- Drawdown span: mean 47.00 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 29.00 | 0.358 | 1.000 | 1.000 | 1.67 |
| <= -10 | 14.00 | 0.173 | 0.667 | 0.500 | 9.00 |
| <= -15 | 6.00 | 0.074 | 0.667 | 0.000 | 8.00 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | -0.093 | [-0.129, -0.057] | insufficient_data |
| `prime_rate_delta` | -0.043 | [-0.062, -0.025] | insufficient_data |
| `search_rate_delta` | +0.074 | [+0.074, +0.074] | insufficient_data |
| `carpet_rate_delta` | -0.019 | [-0.025, -0.012] | insufficient_data |
| `plain_rate_delta` | -0.012 | [-0.025, +0.000] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match (98)`: t30:-6.0/carpet/mid, t48:-6.0/carpet/mid, t36:-4.0/search/mid
- `match - 2026-04-19T030353.361`: t30:-4.0/search/mid, t42:-4.0/carpet/mid, t44:-4.0/search/mid
- `match - 2026-04-19T113051.806`: t20:-4.0/carpet/early, t22:-4.0/search/early, t28:-4.0/search/mid

### segment:opponent_archetype=prime_heavy,map_seed=map:82ef209f,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.333 (CI95 [0.000, 1.000]) | insufficient_data |
| W/L/T | 1/2/0 | - |
| Mean score delta | -7.33 (CI95 [-19.00, +9.00]) | insufficient_data |
| Search conversion | 0.450 (CI95 [0.307, 0.602]) | high_confidence |
| Timeout pressure | 0.000 | - |
| Catastrophic loss | 0.333 (`final score delta <= -15 points`) | - |

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
- PRIME rate (loss/win): 0.426 / 0.407
- Search conversion (loss/win): 0.367 / 0.700

#### Recommended Actions
1. Search conversion is materially worse in losses; tighten belief threshold for SEARCH and raise fallback value floor before committing.
2. Early phase collapses in losses (mean delta change -2.50); tighten opening move safety and reduce high-variance branches in first third.
3. Transition `prime->search` is loss-heavier (gap 0.075); revisit policy thresholds governing this move switch.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +2.00 | -2.50 | +0.00 |
| mid | +4.00 | -5.50 | +0.00 |
| late | +3.00 | -7.50 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->search` | 15 | 0.013 | 0.087 | 0.075 | loss_heavier |
| `plain->plain` | 22 | 0.138 | 0.069 | 0.069 | win_heavier |
| `plain->prime` | 27 | 0.075 | 0.131 | 0.056 | loss_heavier |
| `plain->search` | 13 | 0.087 | 0.037 | 0.050 | win_heavier |
| `search->search` | 6 | 0.000 | 0.037 | 0.037 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 31.0 | 27.5 | 34.5 |
| <= -10 | 1.00 | 54.0 | 47.0 | 61.0 |
| <= -15 | 1.00 | 62.0 | 53.5 | 70.5 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 21.67, median 25.00.
- Drawdown span: mean 29.67 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 23.33 | 0.288 | 0.667 | 1.000 | 3.00 |
| <= -10 | 17.33 | 0.214 | 0.667 | 1.000 | 1.00 |
| <= -15 | 7.00 | 0.086 | 0.667 | 0.500 | 9.50 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | +0.300 | [+0.200, +0.400] | insufficient_data |
| `prime_rate_delta` | -0.019 | [-0.099, +0.062] | insufficient_data |
| `search_rate_delta` | -0.062 | [-0.123, +0.000] | insufficient_data |
| `carpet_rate_delta` | +0.012 | [+0.000, +0.025] | insufficient_data |
| `plain_rate_delta` | +0.068 | [+0.037, +0.099] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match - 2026-04-19T024233.553`: t50:-6.0/carpet/mid, t60:-4.0/search/late, t72:-4.0/search/late
- `match - 2026-04-19T024259.798`: t38:-6.0/carpet/mid, t6:-4.0/carpet/early, t56:-4.0/carpet/late
- `match - 2026-04-19T113210.214`: t14:-10.0/carpet/early, t34:-10.0/carpet/mid, t24:-4.0/search/early

### segment:opponent_archetype=prime_heavy,map_seed=map:7fb4f3df,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.667 (CI95 [0.000, 1.000]) | insufficient_data |
| W/L/T | 2/1/0 | - |
| Mean score delta | +4.67 (CI95 [-3.00, +12.00]) | insufficient_data |
| Search conversion | 0.500 (CI95 [0.345, 0.655]) | high_confidence |
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
- PRIME rate (loss/win): 0.420 / 0.451
- Search conversion (loss/win): 0.538 / 0.478

#### Recommended Actions
- None

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +1.50 | +7.00 | +0.00 |
| mid | +3.00 | -1.00 | +0.00 |
| late | +4.00 | -9.00 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->prime` | 58 | 0.263 | 0.200 | 0.062 | win_heavier |
| `prime->carpet` | 15 | 0.050 | 0.087 | 0.037 | loss_heavier |
| `plain->carpet` | 8 | 0.044 | 0.013 | 0.031 | win_heavier |
| `plain->plain` | 20 | 0.075 | 0.100 | 0.025 | loss_heavier |
| `carpet->prime` | 11 | 0.037 | 0.062 | 0.025 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 0.00 | 0.0 | 0.0 | 0.0 |
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

- Max drawdown: mean 17.67, median 18.00.
- Drawdown span: mean 28.33 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 3.33 | 0.041 | 0.333 | 1.000 | 5.00 |
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
| `search_conversion_delta` | -0.046 | [-0.110, +0.017] | insufficient_data |
| `prime_rate_delta` | +0.031 | [+0.012, +0.049] | insufficient_data |
| `search_rate_delta` | -0.019 | [-0.049, +0.012] | insufficient_data |
| `carpet_rate_delta` | +0.006 | [+0.000, +0.012] | insufficient_data |
| `plain_rate_delta` | -0.019 | [-0.025, -0.012] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match - 2026-04-19T024248.178`: t34:-4.0/search/mid, t36:-4.0/carpet/mid, t40:-4.0/search/mid
- `match - 2026-04-19T113101.078`: t6:-4.0/carpet/early, t38:-4.0/carpet/mid, t46:-4.0/search/mid
- `match - 2026-04-19T122326.622`: t20:-10.0/carpet/early, t26:-2.0/carpet/early, t35:-2.0/search/mid

### segment:opponent_archetype=prime_heavy,map_seed=map:0e3899f9,opening_family=prime_chain

#### Data
| Metric | Value | Confidence |
|---|---|---|
| Win rate | 0.667 (CI95 [0.000, 1.000]) | insufficient_data |
| W/L/T | 2/1/0 | - |
| Mean score delta | +3.00 (CI95 [-7.00, +11.00]) | insufficient_data |
| Search conversion | 0.512 (CI95 [0.365, 0.657]) | high_confidence |
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
- PRIME rate (loss/win): 0.407 / 0.426
- Search conversion (loss/win): 0.529 / 0.500

#### Recommended Actions
1. Early phase collapses in losses (mean delta change -15.00); tighten opening move safety and reduce high-variance branches in first third.

#### Diagnostics: Phase Split (mean delta change)

- What the numbers mean: each cell is average **change in score delta** during that phase (`end_delta - start_delta`).
- Sign: positive means A gains relative points in that phase; negative means A loses relative points.
- How to read: if `Losses` is strongly negative in a phase while `Wins` is near/above zero, that phase is a likely collapse window.

| Phase | Wins | Losses | Ties |
|---|---:|---:|---:|
| early | +2.50 | -15.00 | +0.00 |
| mid | +3.00 | +7.00 | +0.00 |
| late | +2.50 | +1.00 | +0.00 |

#### Diagnostics: Transition Patterns (largest win/loss gaps)

- What the numbers mean: `Win rate`/`Loss rate` are normalized frequencies of that transition within win/loss matches.
- `Gap` is `abs(win_rate - loss_rate)`; larger values indicate stronger behavioral separation between outcomes.
- `Bias`: `loss_heavier` means overrepresented in losses (candidate pattern to reduce), `win_heavier` means overrepresented in wins.
- Only transitions with support >= 5 are shown.
- Rates are turn-weighted (normalized by total transitions), so longer matches contribute more.

| Transition | Support | Win rate | Loss rate | Gap | Bias |
|---|---:|---:|---:|---:|---|
| `prime->prime` | 50 | 0.237 | 0.150 | 0.087 | win_heavier |
| `plain->plain` | 19 | 0.100 | 0.037 | 0.062 | win_heavier |
| `search->prime` | 16 | 0.050 | 0.100 | 0.050 | loss_heavier |
| `plain->prime` | 23 | 0.081 | 0.125 | 0.044 | loss_heavier |
| `search->search` | 6 | 0.013 | 0.050 | 0.038 | loss_heavier |

#### Diagnostics: Deficit Onset (losses)

- What the numbers mean: each row tracks first turn where score delta falls to `<= threshold` for loss matches.
- `Onset rate` = fraction of loss matches that ever cross that threshold.
- `Median/Q1/Q3 turn`: timing of first crossing among crossed matches; lower turns mean earlier collapse, tighter quartiles mean more consistent timing.

| Threshold | Onset rate | Median turn | Q1 | Q3 |
|---|---:|---:|---:|---:|
| <= -5 | 1.00 | 18.0 | 18.0 | 18.0 |
| <= -10 | 1.00 | 22.0 | 22.0 | 22.0 |
| <= -15 | 1.00 | 24.0 | 24.0 | 24.0 |

#### Diagnostics: Trajectory Robustness

- What the numbers mean: these metrics describe **how bad states develop and resolve over time**, not just where the match ended.
- `Max drawdown`: largest drop from any earlier best score-delta point to a later trough; higher means deeper collapses.
- `Mean time in deficit`: average turns spent at or below the threshold; higher means you stay behind longer.
- `Cross rate`: fraction of matches that ever fall below the threshold at least once.
- `Recovery rate after cross`: among matches that crossed, fraction that climbed back above the threshold.
- `Mean recovery latency`: average turns needed to recover after first crossing; lower is better.
- How to interpret: prioritize fixes where cross rate is high, recovery rate is low, and latency is long; those thresholds mark your most stubborn failure regimes.

- Max drawdown: mean 15.33, median 14.00.
- Drawdown span: mean 16.33 turns.

| Threshold | Mean time in deficit (turns) | Mean deficit fraction | Cross rate | Recovery rate after cross | Mean recovery latency |
|---|---:|---:|---:|---:|---:|
| <= -5 | 22.67 | 0.280 | 0.667 | 1.000 | 11.00 |
| <= -10 | 6.33 | 0.078 | 0.333 | 1.000 | 9.00 |
| <= -15 | 1.00 | 0.012 | 0.333 | 1.000 | 3.00 |

#### Diagnostics: Behavior Contrasts (win - loss)

- What the numbers mean: each row compares behavior in wins vs losses as `delta = win_metric - loss_metric`.
- Sign: positive means the behavior appears more in wins; negative means it appears more in losses.
- `CI95`: plausible range for the true delta; if the interval stays on one side of zero, the directional signal is more credible.
- `Confidence`: `high_confidence` means enough sample and CI excludes zero; `medium_confidence` means directional uncertainty remains.
- How to interpret: focus first on large-magnitude deltas with high confidence, then treat medium-confidence rows as hypotheses to validate with more matches.

| Metric | Delta | CI95 | Confidence |
|---|---:|---|---|
| `search_conversion_delta` | -0.029 | [-0.113, +0.054] | insufficient_data |
| `prime_rate_delta` | +0.019 | [+0.000, +0.037] | insufficient_data |
| `search_rate_delta` | -0.062 | [-0.062, -0.062] | insufficient_data |
| `carpet_rate_delta` | +0.019 | [+0.000, +0.037] | insufficient_data |
| `plain_rate_delta` | +0.025 | [-0.012, +0.062] | insufficient_data |

#### Diagnostics: Top Turning Points (per match)
- What the numbers mean: each item lists the largest negative single-turn `delta_change` events in that match.
- Example `t12:-6.0/carpet/early` means on turn 12 the score delta dropped by 6, action mode was `carpet`, phase was `early`.
- How to read: repeated mode/phase signatures across many matches indicate systematic tactical failure patterns to inspect in replays.
- `match - 2026-04-19T024306.597`: t10:-6.0/carpet/early, t38:-4.0/search/mid, t50:-4.0/carpet/mid
- `match - 2026-04-19T112939.358`: t14:-10.0/carpet/early, t56:-4.0/search/late, t68:-4.0/carpet/late
- `match - 2026-04-19T120306.353`: t22:-6.0/carpet/early, t18:-4.0/search/early, t24:-4.0/search/early
