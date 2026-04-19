# M2 time manager profiling report

This artifact satisfies [bot_plan_v4.md](bot_plan_v4.md) **Required Milestone Artifacts → M2**: time-manager profiling under `strict_240` and `local_360`.

Ground truth for formulas: [bot_plan_v4.md](bot_plan_v4.md) Policy Constants Table (phase multipliers, phase caps, anti-burn guard, emergency floor).

## Implementation reference

| Item | Location |
| --- | --- |
| Allocator | [3600-agents/Yolanda/time_manager.py](3600-agents/Yolanda/time_manager.py) |
| Per-turn deadline + emergency exit | [3600-agents/Yolanda/policy.py](3600-agents/Yolanda/policy.py) `select_action` |
| Batch / synthetic sweep | [workflows/m2_competitive_batch.py](workflows/m2_competitive_batch.py) |

## Budget profiles

| Profile | `initial_total_budget` (typical) | `TimeManager.profile_name` |
| --- | --- | --- |
| strict_240 | 240 | `strict_240` |
| local_360 | 360 | `local_360` |

Promotion-style runs should treat **240s** as the strict assignment envelope ([assignment_spec.md](assignment_spec.md) §2.2, §7.5). Local **360s** matches the engine default when `play_game(..., limit_resources=False)` ([engine/gameplay.py](engine/gameplay.py)).

## Formula summary (v4 policy defaults)

- `emergency_floor_total = max(1.2, 0.02 * initial_total_budget)`
- `t_eff = max(0, time_remaining - emergency_floor_total)`; if `t_eff == 0` → emergency mode (zero allocation; policy returns immediately).
- `base = t_eff / max(1, turns_remaining)`
- `alloc_raw = clamp(base * phase_mult, 0.015, phase_cap)`
- `allocation = min(alloc_raw, 0.20 * t_eff)`

Phase multipliers and caps:

| Phase | `turn_count` | Multiplier | Cap (s) |
| --- | --- | --- | --- |
| Early | `< 20` | 1.25 | 4.5 |
| Mid | `20–59` | 1.10 | 3.0 |
| Late | `>= 60` | 0.90 | 1.5 |

## Synthetic allocation sweep (deterministic)

The workflow emits a full markdown table over representative `(turn_count, time_remaining, turns_left)` tuples (no engine subprocess). Regenerate anytime:

```bash
.venv/bin/python workflows/m2_competitive_batch.py --synthetic-table
```

### strict_240 (excerpt)

Representative rows at `initial_total_budget=240` (`emergency_floor_total ≈ 4.8s`):

| turn_count | phase | t_rem | turns_left | alloc (s) | emergency |
| --- | --- | --- | --- | --- | --- |
| 0 | early | 120.00 | 20 | 4.5000 | False |
| 0 | early | 20.00 | 20 | 0.9500 | False |
| 19 | early | 60.00 | 5 | 4.5000 | False |
| 20 | mid | 120.00 | 20 | 3.0000 | False |
| 59 | mid | 60.00 | 20 | 2.3100 | False |
| 60 | late | 120.00 | 20 | 1.5000 | False |
| 60 | late | 10.00 | 5 | 0.5200 | False |

Observations:

- Per-turn allocation never exceeds the phase cap or `0.20 * t_eff`.
- Near `t_rem ≈ emergency_floor + 0.5`, allocations shrink toward the minimum turn budget (`0.015s`) before emergency triggers at `t_eff == 0`.

### local_360 (excerpt)

Same grid with `initial_total_budget=360` (`emergency_floor_total = max(1.2, 7.2) = 7.2s`):

| turn_count | phase | t_rem | turns_left | alloc (s) | emergency |
| --- | --- | --- | --- | --- | --- |
| 0 | early | 120.00 | 20 | 4.5000 | False |
| 60 | late | 120.00 | 20 | 1.5000 | False |

Larger initial budget only changes `emergency_floor_total` and the scale of `t_eff`; phase caps and multipliers are unchanged.

## Live match notes

- [workflows/m2_competitive_batch.py](workflows/m2_competitive_batch.py) was run under **strict** (`play_time=240`) and **local** (`play_time=360`) with `seed_start=42`, `games=4`, `quiet` mode: **zero** timeout / invalid / crash outcomes in those runs (see [m2_tactical_ab_summary.md](m2_tactical_ab_summary.md)).
- On **macOS**, `m2_competitive_batch.py` defaults to `limit_resources=False` even for `profile=strict` (RLIMIT behavior); use Linux or explicit `--limit-resources` for restricted-mode smoke when available ([workflows/quality_guard.md](workflows/quality_guard.md)).

## Pass criteria (M2)

- Allocator matches v4 table (covered by unit tests in [tests/test_time_manager.py](tests/test_time_manager.py) and synthetic sweep).
- Batch reliability: no timeout losses for Yolanda in the recorded strict/local sample runs; expand `games` for stronger statistical confidence before milestone promotion.
