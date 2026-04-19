# M2 tactical A/B summary

This artifact satisfies [bot_plan_v4.md](bot_plan_v4.md) **Required Milestone Artifacts → M2**: tactical A/B summary.

## Experiment design

**A (treatment):** [Yolanda](3600-agents/Yolanda/) — full `PolicyEngine` with belief-informed search cell choice, multi-term tactical scorer, v4 time manager.

**B (control):** [RandomSearchBaseline](3600-agents/RandomSearchBaseline/) — same candidate generation and time guards, but **uniform random** choice among legal search candidates when a search action is taken ([3600-agents/RandomSearchBaseline/policy.py](3600-agents/RandomSearchBaseline/policy.py)).

Both agents share belief updates and explicit search inclusion (M1 core). The A/B isolates **search targeting + tactical ranking** versus **random search targeting**.

## Protocol

- Harness: [workflows/m2_competitive_batch.py](workflows/m2_competitive_batch.py)
- Side alternation: even game index → Yolanda as player A; odd → Yolanda as player B
- Seeds: `random.seed(seed_start + g)` with `seed_start=42`
- Metrics: wins (Yolanda as arbiter winner), mean final score delta (Yolanda − baseline), search attempts / correct / precision, reliability counts (timeout, invalid, crash)

## Results (recorded sample)

Command:

```bash
.venv/bin/python workflows/m2_competitive_batch.py --games 4 --quiet --profile strict --seed-start 42
.venv/bin/python workflows/m2_competitive_batch.py --games 4 --quiet --profile local --seed-start 42
```

### strict profile (`play_time=240`)

| Metric | Value |
| --- | --- |
| Yolanda wins / ties / baseline wins | 4 / 0 / 0 |
| Mean score delta (Yolanda − RandomSearchBaseline) | +66.25 |
| Yolanda search precision (correct / attempts) | 32 / 89 ≈ 0.360 |
| Baseline search precision | 1 / 113 ≈ 0.009 |
| Timeout / invalid / crash (all games) | 0 / 0 / 0 |
| Yolanda timeout losses | 0 |

### local profile (`play_time=360`)

| Metric | Value |
| --- | --- |
| Yolanda wins / ties / baseline wins | 4 / 0 / 0 |
| Mean score delta | +74.00 |
| Yolanda search precision | 34 / 89 ≈ 0.382 |
| Baseline search precision | 6 / 125 ≈ 0.048 |
| Timeout / invalid / crash | 0 / 0 / 0 |
| Yolanda timeout losses | 0 |

## Interpretation

- Mean score differential is **strongly positive** versus the random-search control on identical seeds, matching M2 acceptance (“positive score differential vs baseline pool”) from [bot_plan_v4.md](bot_plan_v4.md).
- Search precision gap shows the control wastes search EV by guessing uniformly; Yolanda’s posterior-driven targets align with [assignment_spec.md](assignment_spec.md) §10.6 (`EV = 6P − 2`).
- For promotion, run a larger `--games` grid under **strict_240** with `limit_resources=True` on Linux and keep timeout rate at **0%** per bot_plan reliability targets.

## Reproduction

```bash
./validate_m2.sh
```

Or manually increase statistical power:

```bash
.venv/bin/python workflows/m2_competitive_batch.py --games 32 --quiet --profile strict --seed-start 42
```
