# Deep Research Plan v5 (Ground-Truth Complete, Decision-Complete + Final Rat Policy Swap)

## Objective
Produce a canonical, implementation-ready plan for the strongest practical agent in this repository, with `assignment_spec.md` as strict ground truth.

Primary goals:

- Maximize competitive performance with measurable gates.
- Preserve strict rule and engine correctness.
- Remove implementation ambiguity for AI coding agents.
- Keep optional strategy layers explicitly separated from required behavior.

Normative tags:

- `[Required by engine]`
- `[Required by assignment]`
- `[Policy default in v4]` — Recommended starting-point decisions chosen as best practical defaults. Not required by engine or assignment, but selected for initial implementation. May be refined through tuning.
- `[Optional optimization]`
- `[Speculative]`

Status labels used in audit sections:

- `Exact`
- `Compatible`
- `Conflict`
- `Unsupported`
- `Optional`

Canonical precedence:

1. `assignment_spec.md`
2. Engine behavior summarized by `assignment_spec.md`
3. Strategy recommendations in prior planning docs (`deep_research_plan.md`, `deep_research_plan_v2.md`, `deep_research_plan_v3.md`)

---

## Performance Targets

### Reliability and Core Strength Contract

| Metric | Definition | Target | Failure Threshold | Measurement |
| --- | --- | --- | --- | --- |
| Invalid-turn rate | Fraction of turns resulting in invalid move terminal loss | `0.0%` in validation suite | `>0.1%` | Scripted legality suite + batch self-play |
| Timeout loss rate | Fraction of games lost by timeout-like outcomes | `0.0%` in stress matrix | `>0.5%` | Multi-budget match grid |
| Crash/failure rate | Fraction of games ending by crash/init/memory failure | `0.0%` | `>0.1%` | Automated log scan over repeated games |
| Elo lift vs M2 baseline | Elo gain after M3/M4 upgrades | `+120` minimum | `< +60` | Fixed-seed A/B tournament harness |
| Search precision | Correct searches / total searches | `>=45%` | `<33%` | Match telemetry parsing |
| Score differential | Mean final score delta vs baseline pool | Positive and non-regressing | Non-positive after M2 | Aggregated match stats |
| Win rate vs random baseline | Win rate against random/legal-move bot | `>=85%` | `<70%` | 200+ game evaluation grid |
| Win rate vs heuristic baseline | Win rate against non-search heuristic bot | `>=65%` | `<50%` | 200+ game evaluation grid |

Interpretation:

- These are implementation gates, not guarantees. `[Required by assignment]`
- Reliability gates dominate optimization gates: no advancement with reliability regressions. `[Required by engine]`

---

## Ground-Truth Constraints

### Core constants and rules

| Item | Ground Truth | Tag | Source in `assignment_spec.md` |
| --- | --- | --- | --- |
| Board size | `8 x 8` | `[Required by assignment]` | §2.1, Appendix A.1 |
| Turn budget | `40` per player (`80` total cap) | `[Required by engine]` | §2.1, §5.7 |
| Prime scoring | `+1` | `[Required by engine]` | §2.3, §5.4 |
| Carpet scoring | `{1:-1,2:2,3:4,4:6,5:10,6:15,7:21}` | `[Required by engine]` | §2.3, §3.6 |
| Search scoring | Correct `+4`, incorrect `-2` | `[Required by engine]` | §2.3, §5.4 |
| Rat spawn model | Start `(0,0)` then `1000` hidden moves, same after successful capture | `[Required by engine]` | §2.5, §6.3 |
| Noise categories | `SQUEAK`, `SCRATCH`, `SQUEAL` | `[Required by engine]` | §2.7, §6.4 |
| Rat occupancy rule | Rat can move onto and through blocked squares; belief posterior must cover all 64 cells | `[Required by engine]` | §2.5 |
| Spawn positions | Both players spawn in center `4x4` region, horizontally mirrored; opponent start position is inferable | `[Required by assignment]` | §2.4 |
| Corner blockers | Each corner gets a randomly selected blocked rectangle from `{3x2, 2x3, 2x2}` | `[Required by assignment]` | §2.4 |
| Noise emission table | `BLOCKED={SQ:0.50,SC:0.30,SL:0.20}`, `SPACE={SQ:0.70,SC:0.15,SL:0.15}`, `PRIMED={SQ:0.10,SC:0.80,SL:0.10}`, `CARPET={SQ:0.10,SC:0.10,SL:0.80}` | `[Required by engine]` | §6.4, Appendix A.3 |
| Distance error distribution | Offset from true Manhattan: `{-1:0.12, 0:0.70, +1:0.12, +2:0.06}`; reported distance clipped to `max(0, ...)` | `[Required by engine]` | §6.5, Appendix A.4 |

### API and runtime constraints

| Item | Ground Truth | Tag | Source in `assignment_spec.md` |
| --- | --- | --- | --- |
| Agent methods | `__init__(board, transition_matrix, time_left)`, `play(board, sensor_data, time_left)`, `commentate()` | `[Required by engine]` | §3.1 |
| Search generation default | `get_valid_moves(..., exclude_search=True)` by default | `[Required by engine]` | §3.4, §9 |
| Search tuple behavior | Search channel result is tri-state (`True/False/None`) over runtime flow | `[Required by engine]` | §3.3, §4, §9 |
| Transition matrix mutation | Per-game matrix perturbed in `[-10%, +10%]`, clamped, renormalized | `[Required by engine]` | §6.1, §9 |
| Time semantics | Assignment intent `240s`; local unrestricted defaults commonly `360s` | `[Required by engine]` | §7.5, §9 |
| Constructor timeout windows | Constructor has separate bounded timeout (`10s` restricted / `20s` local default) | `[Required by engine]` | §7.2, §9 |
| Missing-move classification nuance | Queue timeout-like failure path may surface as `CODE_CRASH` via `timer == -1` | `[Required by engine]` | §4, §9 |
| Zip size limit | Submission archive must be `<= 200 MB` | `[Required by assignment]` | §2.9 |
| Environment restrictions | No network requests; no reads/writes outside working directory; no external code/data not created by team | `[Required by assignment]` | §2.9 |
| `forecast_move` method | `board.forecast_move(move, check_ok=True)` returns new board copy without mutating original; use for non-destructive simulation lookahead | `[Required by engine]` | §3.4 |
| Multi-file package structure | Agent package requires `__init__.py` with `from .agent import PlayerAgent`; use relative imports for submodules | `[Required by assignment]` | §2.10 |

---

## Engine Nuances That Affect Strategy

1. Search actions are omitted by default helper behavior unless explicitly included. `[Required by engine]`
2. Search score and rat respawn are handled in game loop semantics, not only board mutation helpers. `[Required by engine]`
3. Search telemetry channels must be parsed tri-state (`True/False/None`). `[Required by engine]`
4. Timeout tie behavior has an overwrite nuance in post-apply checks; planner must avoid edge-case debt. `[Required by engine]`
5. Local unrestricted testing does not prove resource-limited tournament readiness. `[Required by assignment]`
6. Winner semantics are perspective-relative in-loop and remapped to absolute at match end. `[Required by engine]`

---

## Discrepancy Completeness Matrix (Full §9 Lock)

Fixed schema columns: `Rule`, `Engine Truth`, `Implementation Rule`, `Test Case`, `Pass Condition`, `Source`.

| Rule | Engine Truth | Implementation Rule | Test Case | Pass Condition | Source |
| --- | --- | --- | --- | --- | --- |
| Total time budget duality | Assignment intent is `240s`; local unrestricted default commonly `360s` | Develop and validate under both envelopes; tune against stricter `240s` budget for safety | Run identical match set under both budget profiles | No reliability regression under `240s`; policy behavior stable | `assignment_spec.md` §7.5, §9 |
| Search generation default exclusion | `get_valid_moves` defaults `exclude_search=True` | Candidate generator must explicitly include search path | Unit-test move generation with/without explicit search inclusion | Search candidates present only when explicitly enabled; never omitted by accident | §3.4, §9 |
| Transition matrix perturbation | Runtime matrix is perturbed, clamped, renormalized per game | Treat constructor-provided matrix as canonical per-match matrix | Verify belief update uses provided runtime matrix, not static `.pkl` assumptions | Belief module consumes injected matrix only | §6.1, §9 |
| Noise category mismatch in prose | Runtime uses three categories including `SQUEAL` | Observation likelihood model must support all three categories | Feed synthetic sensor data with each noise enum | Likelihood pipeline accepts all three without fallback errors | §2.7, §6.4, §9 |
| Search scoring location | Search score/respawn occur in gameplay loop, not board `apply_move` | Planner rollouts that use board helpers must manually model search score + respawn | Simulate search action via rollout adapter and compare with gameplay semantics | Adapter outcome equals gameplay-contract outcome | §5.4, §9 |
| Search tuple tri-state typing | Non-search turns can publish `(None, None)` | Parse search result as tri-state and branch null-safely | Replay mixed search/non-search history stream | Parser preserves `None` without coercion to `False` | §3.3, §4, §9 |
| Missing-move classification nuance | Timeout-like queue wait path can map to `CODE_CRASH` | Reliability metrics must count timeout-like crash-class outcomes in failure bucket | Inject forced delayed-return scenarios in harness | Failure taxonomy logs and gates classify outcome consistently | §4, §9 |
| Timeout tie overwrite nuance | `check_win` tie logic can be overwritten by post-apply timeout check | Avoid near-boundary debt; maintain explicit emergency floor before action return | Stress test with near-zero residual time states | No late-turn debt enters overwrite zone in validated policy | §5.7, §9 |
| Invalid search side effects | Invalid search can still run search side-effect branch in loop | Policy should prevent invalid search generation entirely; tests must assert no invalid search path | Negative test with intentionally malformed search move in simulation harness | Production policy emits zero invalid search moves | §4, §9 |
| Local vs restricted runtime gap | Local default may skip seccomp/resource limits | Add restricted-mode readiness checks in test plan before milestone promotion | Run smoke suite in unrestricted and restricted modes | Core features pass in both modes; no prohibited assumptions | §7.4, §7.5, §9 |
| Constructor timeout policy | Constructor has strict timeout window separate from game budget | Keep constructor deterministic and lightweight; defer heavy work to cached lazy init | Constructor stress run with cold start | Constructor completes under enforced timeout window | §7.2, §9 |
| Opponent search reporting channel nuance | `opponent_search` and `player_search` are rolling channels post perspective swap | Evidence integration must use channel semantics exactly as provided post-swap | Replay known sequence and assert mapped channel interpretation | Own and opponent search evidence consumed in correct temporal order | §4, §9 |
| Winner representation remap | In-loop winner is perspective-relative then remapped to absolute arbiter winner | Evaluation and logging must avoid assuming absolute winner mid-loop | Parse history snapshots during and after game end | Mid-loop metrics stay perspective-safe; end-of-game metrics use arbiter winner | §4, §9 |
| Worker default time constant nuance | Worker default is `240`, but board constructor can override at runtime | Always use current runtime time fields/callables; never hardcode assumed initial total | Initialize games under differing budget constants | Time manager behavior derives from runtime value only | §3.3, §9 |

---

## Strategy Stack (Baseline / Competitive / Elite)

### Baseline (must ship first)

1. 64-cell belief tracker with transition + observation update per turn. `[Required by engine]`
2. Deterministic tactical scorer with immediate points, mobility, carpet potential, and trap penalties. `[Policy default in v4]`
3. Explicit search action generation and search EV comparison path. `[Required by engine]`
4. Strict time guard with guaranteed fallback action return. `[Policy default in v4]`

### Competitive (incremental upgrade)

1. Bounded depth-limited adversarial simulation with hard interrupt checks. `[Optional optimization]`
2. Opponent-aware tactical features (mobility denial, corridor control, carpet-lane contesting). `[Optional optimization]`
3. Adaptive search margin based on score state, tempo, and residual time. `[Optional optimization]`

### Elite (max-practical)

1. Anytime planner layer (bounded IS-MCTS hybrid) over tactical baseline. `[Optional optimization]`
2. Offline tuning loop with seed sweeps and ablations. `[Optional optimization]`
3. Optional state-feature caching for recurring motifs. `[Optional optimization]`
4. Optional external acceleration for large parameter sweeps. `[Speculative]`

---

## Decision Policy Specification

### Policy Contract

| State Inputs | Belief Inputs | Action Set | Priority Rules | Fallback Rule | Timing Guard |
| --- | --- | --- | --- | --- | --- |
| Board perspective, worker states, score/time/turns, masks, search channels | Posterior over 64 cells, top-k mass cells, entropy proxy | Legal movement actions + explicit search candidates | (1) reliability/legality, (2) tactical safety, (3) EV comparison search vs non-search, (4) deterministic tie-break order | Best valid tactical action under emergency mode | Hard stop on emergency floor; return immediately |

### Per-Turn Decision Flow

Execute in strict order each turn:

1. **Ingest state**: Read `board`, `sensor_data = (noise, estimated_distance)`, and `time_left()`. Compute per-turn budget using allocation formula from Policy Constants Table. `[Required by engine]`
2. **Check time guard**: If `time_left() <= emergency_floor_total`, enter emergency mode immediately: return best cached action or first valid action. Skip all subsequent steps. `[Policy default in v4]`
3. **Update belief**: Apply exact HMM with the final timing rules. Use `T` for one post-reset untracked step and `T2` for two-step/default play. On opponent miss at `g`, apply split-step integration (`B@T`, zero `g`, renormalize, `@T`) before observation update. On self miss at `g`, zero current posterior at `g` and renormalize. On any successful search, reset to cached `b_reset = e0 @ T^1000` and update post-respawn step flag. `[Required by engine]`
4. **Generate candidates**: Get movement actions from `board.get_valid_moves()`. Explicitly add search candidates via `Move.search((x, y))` for top-k posterior cells per search candidate cap. Validate all candidates with `board.is_valid_move()`. `[Required by engine]`
5. **Score and compare**: For `r_me > 3`, use standard guess gate `6*p1 - 2 >= Q_best_non + 0.5` (no separate hard floor, no opponent-denial modifier in threshold). For `r_me <= 3`, switch objective to win probability with exact greedy rollout `M_non(board,k)` for both players and apply must-guess override if `S_me + M_non(my_board,r_me) <= E_opp_final`. `[Policy default in v5]`
6. **Select and return**: Choose highest-ranked action per priority rules. If planner exceeds per-turn budget, apply fail-safe order. Return `Move` object before timing guard threshold. `[Required by engine]`

### Policy Constants Table

Fixed schema columns: `Rule`, `Engine Truth`, `Implementation Rule`, `Test Case`, `Pass Condition`, `Source`.

| Rule | Engine Truth | Implementation Rule | Test Case | Pass Condition | Source |
| --- | --- | --- | --- | --- | --- |
| Per-turn budget input variables | Engine exposes `time_left()` plus turn counters | Compute `turns_remaining = max(1, board.player_worker.turns_left)` and `t = time_left()` | Snapshot several board states with varying `turns_left` and `time_left` | Inputs are read from runtime state each turn | `assignment_spec.md` §3.2, §5.5, §10.3 |
| Budget allocation formula | No fixed engine formula provided | `base = (t - emergency_floor_total) / turns_remaining` | Evaluate formula against synthetic early/mid/late inputs | Base allocation is computed deterministically from runtime values | `[Policy default in v4]` |
| Effective remaining-time guard | Engine only enforces total-time loss boundary | Compute `t_eff = max(0, t - emergency_floor_total)` before any cap logic | Near-floor time simulations | Effective time never negative; no downstream negative budgets | `[Policy default in v4]` |
| Phase multipliers | Engine does not prescribe phase multipliers | Early (`turn_count < 20`): `1.25`; Mid (`20-59`): `1.10`; Late (`>=60`): `0.90` | Simulated turn progression | Multiplier selection deterministic by `turn_count` | `[Policy default in v4]` |
| Phase caps | Engine does not prescribe per-phase hard caps | Early: `4.5s`; Mid: `3.0s`; Late: `1.5s` | Time profiling under all three phases | Per-turn allocation never exceeds phase cap | `[Policy default in v4]` |
| Global emergency floor | Engine only defines total-budget loss condition | Set `emergency_floor_total = max(1.2, 0.02 * initial_total_budget)` seconds, where `initial_total_budget` is captured from first-turn `time_left()` value | Near-zero budget stress tests | Planner exits early and fallback returns action before floor breach | `[Policy default in v4]` |
| Per-turn minimum and anti-burn guard | Engine has no agent-side anti-burn allocation rule | Use `min_turn_budget = 0.015s`; `alloc_raw = clamp(base * phase_mult, min_turn_budget, phase_cap)`; `alloc = min(alloc_raw, 0.20 * t_eff)`. If `t_eff == 0`, return emergency fallback immediately | Time profiling under low, medium, and high residual budgets | No allocation is negative; allocation never exceeds `20%` of effective remaining time | `[Policy default in v4]` |
| Evaluation budget profiles | Assignment intent is `240s`; local unrestricted runs can use `360s` | Maintain explicit profiles: `strict_240` and `local_360`. Milestone promotion requires reliability gates to pass under `strict_240`; `local_360` is throughput-only for exploratory runs | Run identical suite under both profiles | Promotion blocked unless strict profile passes all reliability gates | `assignment_spec.md` §7.5, §9 |
| Search EV function | Search payoff model is fixed (`+4/-2`) | Use `EV_search(c) = 6 * P(c) - 2` for each candidate search cell | Symbolic and numeric unit tests | EV implementation matches analytic formula | `assignment_spec.md` §10.6 |
| Standard-mode search gate (`r_me > 3`) | Engine does not prescribe threshold policy | Trigger search iff `6*p1 - 2 >= Q_best_non + 0.5`, where `Q_best_non` is best immediate legal non-search gain (Prime=1, Carpet table, Plain=0) | Scenario matrix across board states and score/time regimes | Gate decisions match formula exactly; no separate hard floor on `p1` | `[Policy default in v5]` |
| Search candidate cap | Engine allows all 64 locations | Evaluate top-`k=6` posterior cells + optional local neighborhood expansion of radius 1 | High-entropy and low-entropy belief tests | Search branch count bounded; top-mass cell always included | `[Policy default in v4]` |
| Horizon switch | Engine does not prescribe objective switch | Standard mode strictly when `r_me > 3`; endgame mode strictly when `r_me <= 3` | Boundary tests at `r_me in {3,4}` | Correct branch selected on boundary | `[Policy default in v5]` |
| Endgame projections (`r_me <= 3`) | Engine does not prescribe rollout depth policy | Compute `M_non(board,k)` via exact greedy non-search rollout for both self and opponent; `E_opp_final = S_opp + M_non(opp_board,r_opp)` | Deterministic rollout parity tests | Endgame decisions use rollout values, not heuristic proxies | `[Policy default in v5]` |
| Must-guess override | Engine does not prescribe desperation gate | Force search when `S_me + M_non(my_board,r_me) <= E_opp_final` | Endgame catch-up scenarios | Search forced exactly when inequality holds | `[Policy default in v5]` |
| Initial tactical coefficients | Engine does not prescribe heuristic weights | Start at `a=1.00, b=0.45, c=0.60, d=0.35, e=1.00, f=0.75` in `S_total = a*S_immediate + b*S_position + c*S_carpet_setup + d*S_denial + e*S_search - f*S_risk`. In production ranking, apply `S_total` only to non-search candidates (`S_search=0`) and score search by `EV_search` | Offline replay scoring sensitivity sweep | Coefficients are loaded deterministically and logged | `[Policy default in v4]` |
| Coefficient retuning schedule | Engine provides no tuning schedule | Retune only at M3/M4 with fixed-seed ablations; reject if reliability gates regress | Ablation run with gate checks | New coefficients accepted only when all gates pass | `[Policy default in v4]` |
| Tie-break deterministic order | Engine does not define agent tie-break policy | Priority: (1) legality confidence, (2) mobility next turn, (3) carpet continuation, (4) lower compute risk, (5) stable move hash order | Construct near-equal action-score scenarios | Chosen action is deterministic across reruns with same seed/state | `[Policy default in v4]` |

### Scoring Component Definitions

Each term in `S_total = a*S_immediate + b*S_position + c*S_carpet_setup + d*S_denial + e*S_search - f*S_risk` for non-search candidate scoring:

| Component | Definition | Computation Method |
| --- | --- | --- |
| `S_immediate` | Direct point gain from this non-search action | Prime: `+1`. Carpet of length `k`: carpet table lookup. Plain: `0`. |
| `S_position` | Mobility and centrality after move | Count legal moves from destination (non-blocked, non-primed, non-occupied neighbors). Add centrality bonus: `centrality = 1.0 - manhattan_dist(dest, (3.5, 3.5)) / 7.0`. Total: `legal_move_count / 4.0 + 0.3 * centrality`. |
| `S_carpet_setup` | Projected high-value carpet roll potential | For each cardinal direction from destination, count contiguous primed cells (`k`). If `k >= 2`, score is `carpet_table[min(k, 7)]`. Take max across all directions; `0` if no direction has `k >= 2`. If action is prime, include newly primed cell in projection. |
| `S_denial` | Opponent mobility suppression | Compute opponent legal move count on projected board state (via `forecast_move` then `get_valid_moves(enemy=True)`). `S_denial = max(0, 8 - opponent_moves) / 8`. Higher when opponent is more constrained. |
| `S_search` | Search EV placeholder for unified ablation logging | In production non-search scoring, set to `0`. Search actions are ranked separately by `EV_search = 6 * P(cell) - 2`. |
| `S_risk` | Penalty for dangerous post-move states | `S_risk = max(0, 1.0 - post_move_legal_moves / 4.0)`. Add `+0.3` if destination has a single exit into a primed-cell chokepoint. |

Component normalization: Each component operates on its natural scale `[0, ~1]` except `S_immediate` which uses point values. Coefficients `a-f` absorb scale differences. Starting coefficients are educated defaults; retune at M3/M4 via fixed-seed ablation sweeps.

### Candidate generation rules

1. Generate movement actions from board helper methods.
2. Explicitly add search actions:
   - by `exclude_search=False`, or
   - by manual `Move.search((x, y))` construction using policy candidate cap.
3. Drop any candidate failing legality checks in current perspective.
4. Enforce deterministic ordering before scoring to guarantee reproducibility.

### Fail-safe order

1. Planner output (if within budget and validity checks pass)
2. Tactical scorer best action
3. Safe heuristic fallback action
4. Last-resort valid plain move

### Hard stop timing behavior

- Evaluate timing guard at each planner iteration.
- Exit planner immediately when emergency floor is reached.
- Never run post-selection expensive recomputation once in emergency mode.

---

## Time Management Policy

1. Treat `time_left()` as authoritative in constructor and `play`. `[Required by engine]`
2. Keep constructor lightweight and deterministic under constructor timeout window. `[Required by engine]`
3. Use policy formula and caps from `Policy Constants Table`. `[Policy default in v4]`
4. Maintain emergency reserve for IPC/serialization overhead. `[Required by engine]`
5. Use in-loop periodic checks to enforce anytime interruption.

---

## Simulation Fidelity Contract

Fixed schema columns: `Rule`, `Engine Truth`, `Implementation Rule`, `Test Case`, `Pass Condition`, `Source`.

| Rule | Engine Truth | Implementation Rule | Test Case | Pass Condition | Source |
| --- | --- | --- | --- | --- | --- |
| Search scoring parity | Search score is applied in gameplay loop, not `Board.apply_move` | Rollout adapter must inject `+4/-2` scoring on search outcome | Compare adapter rollout vs gameplay turn transcript on known states | Point deltas match gameplay semantics exactly | `assignment_spec.md` §5.4, §9 |
| Search success rat reset parity | On successful search, rat respawns from `(0,0)` plus `1000` hidden moves | After successful search, reset belief to cached post-spawn prior `e_0 @ T^1000`; additionally set post-respawn matrix flag (`use_single_step=True` on opponent hit, `False` on own hit). | Controlled belief test with forced successful search events (self/opponent) | Post-search prior and step-flag transitions match policy in both ownership cases | §2.5, §6.3, §10.4 |
| Invalid-search side-effect awareness | Invalid search can still pass side-effect branch in game loop | Policy must prevent invalid search generation; simulation harness must still model engine nuance for diagnostics | Inject invalid search into diagnostic-only simulation path | Diagnostic path reproduces engine behavior; production path emits none | §4, §9 |
| Perspective-swap consistency | Board perspective swaps each turn; search channels updated after swap | Rollout state transition must apply swap ordering before reading search channels | Replay two-turn sequence and validate channel interpretation | `opponent_search/player_search` semantics match engine order | §4, §10.5 |
| Search tuple tri-state parsing | Non-search events may carry `None` result values | Belief evidence update must ignore unknown result values safely | Stream mixed `(loc, True/False/None)` records | No parser crashes or false coercion of `None` | §3.3, §9 |
| Opponent-miss temporal evidence parity | Opponent miss evidence applies at opponent time step (one step before our observation) | Implement split-step propagation: `B@T`, zero missed cell, renormalize, then `@T` before applying current observation likelihood | Controlled sequence with opponent miss between our turns | Posterior matches split-step reference and differs from invalid zero-after-`T2` shortcut | §3.3, §6.3, §9 |
| Winner semantics consistency | In-loop result is perspective-relative; end winner remapped | Rollout/eval metrics must be perspective-safe mid-simulation | Compare mid-loop and terminal logs in mirrored roles | Metrics avoid sign inversion errors | §4, §9 |

---

## Opponent Modeling

Use bounded-complexity opponent profiling for stable gains without fragility.

### Tracked Features

1. **Move-tendency profile**: Classify opponent as prime-heavy, carpet-heavy, or search-heavy based on observed action distribution over recent turns.
2. **Trap-risk profile**: Track corridor entry frequency and post-move mobility counts. Flag opponents that frequently enter low-exit positions.
3. **Search calibration profile**: Track observed search accuracy (correct/total). Track timing of search attempts relative to game phase.
4. **Positional tendency**: Track whether opponent favors central control vs edge play, and directional bias in movement.

### Adaptive Weighting Rules

Apply bounded adaptation with explicit confidence weighting. Raw pattern deltas come from the table below, but only bounded, confidence-weighted deltas are allowed to affect live policy coefficients.

| Opponent Pattern | `delta_raw` | Rationale |
| --- | --- | --- |
| High trap susceptibility (enters low-exit states frequently) | Increase `d` (denial weight) by `+0.15` | Exploit containment opportunity |
| Aggressive search with weak precision (`accuracy < 0.25`) | Increase `a` (immediate) by `+0.10`, decrease own search margin by `-0.05` | Punish opponent's wasted turns with stable scoring |
| Mobility-conservative (rarely enters contested areas) | Increase `c` (carpet setup) by `+0.10` | Prioritize long carpet chains while opponent avoids conflict |
| Prime-heavy opponent (building walls aggressively) | Increase `f` (risk weight) by `+0.10` | Avoid being trapped by opponent's prime walls |
| Search-heavy opponent (`> 30%` turns are searches) | Decrease own search margin by `-0.05` | Both players benefit from search when rat concentrated; don't fall behind |

### Confidence and Bounded Adaptation Math

Per adaptation checkpoint:

- `delta_raw` is the aggregate adjustment from matched opponent-pattern rows.
- `confidence = clamp((observed_turns - 5) / 10, 0, 1) * (1 - behavior_entropy_norm)`.
- `delta_applied = confidence * delta_raw`.
- If `confidence < 0.35`, set all adaptive deltas to `0`.

### Clamp Contracts

Per-parameter adaptive delta clamps:

- `Δa in [-0.10, +0.10]`
- `Δc in [-0.10, +0.10]`
- `Δd in [-0.15, +0.15]`
- `Δf in [-0.10, +0.10]`
- `Δsearch_margin in [-0.10, +0.10]`

Absolute coefficient envelopes after adaptation:

- `a in [0.80, 1.20]`
- `b in [0.30, 0.60]`
- `c in [0.45, 0.75]`
- `d in [0.20, 0.55]`
- `e in [0.80, 1.20]`
- `f in [0.55, 0.95]`

### Stability Rules

- Recompute adaptation every `2` turns only (not every turn).
- Adaptation is disabled until `observed_turns >= 6`.
- On each checkpoint, apply delta clamps first, then absolute envelopes.

---

## Risk Register and Mitigations

| Risk | Impact | Likelihood | Mitigation | Tag |
| --- | --- | --- | --- | --- |
| Omitted search actions from default helper | Severe: no rat captures, major scoring loss | High | Explicit search candidate generation in every turn; tested in M0 | `[Required by engine]` |
| Timeout from deep planner computation | Immediate game loss | Medium | Hard timing guard with emergency floor + anytime interruption + fail-safe order | `[Policy default in v4]` |
| Misparsed search telemetry (`None` coercion) | Belief corruption, incorrect search decisions | Medium | Tri-state parser with null-safe branching; tested in M0 | `[Required by engine]` |
| Belief drift from transition matrix mismatch | Accumulated EV errors in search decisions | Medium | Use only constructor-provided runtime matrix; never reference `.pkl` files | `[Required by engine]` |
| Self-trapping in low-exit positions | Wasted turns, potential mobility death | Medium | `S_risk` penalty in scorer + trap-aware candidate pruning | `[Policy default in v4]` |
| Overfit tuning to narrow seed set | Fragile tournament performance | Medium | Mixed fixed/random seed protocols; regression gates block promotion | `[Optional optimization]` |
| Constructor timeout under restricted mode | Failed init, immediate game loss | Medium | Keep constructor lightweight; cache expensive computations lazily; test under `10s` window | `[Required by engine]` |
| Local-only validation masks tournament failures | Passes locally, fails in restricted sandbox | Medium | Run readiness checks under both modes before milestone promotion | `[Required by assignment]` |
| Architecture complexity delays deadline | Incomplete agent at submission | High | Baseline-first milestone gating; never advance with reliability regressions | `[Required by assignment]` |

---

## Grade Alignment Evaluation Contract

Reference bot behavior (from `assignment_spec.md` §2.12):

- **George**: No lookahead. Extends primes and rolls carpet opportunistically. Opportunistic search. Baseline difficulty.
- **Albert**: Expectiminimax with simple heuristic plus HMM rat tracking. Moderate difficulty.
- **Carrie**: Albert's structure plus stronger cell-potential and distance heuristic. Highest reference difficulty.

Strategic implications: George is beatable by any coherent prime/carpet strategy. Albert requires belief-informed search and reasonable positional play. Carrie requires strong spatial denial, carpet maximization, and precise search timing.

Fixed schema columns: `Rule`, `Engine Truth`, `Implementation Rule`, `Test Case`, `Pass Condition`, `Source`.

| Rule | Engine Truth | Implementation Rule | Test Case | Pass Condition | Source |
| --- | --- | --- | --- | --- | --- |
| Grade gate vs George | Assignment references `>=70%` threshold | Include explicit George gate in final acceptance pack | Platform scrimmage set vs George | Win rate `>=70%` | `assignment_spec.md` §2.12 |
| Grade gate vs Albert | Assignment references `>=80%` threshold | Include explicit Albert gate in final acceptance pack | Platform scrimmage set vs Albert | Win rate `>=80%` | §2.12 |
| Grade gate vs Carrie | Assignment references `>=90%` threshold | Include explicit Carrie gate in final acceptance pack | Platform scrimmage set vs Carrie | Win rate `>=90%` | §2.12 |
| ELO linkage | Ranking and grading interpolation are ELO-based | Track ELO trend for every milestone release candidate | Platform or equivalent ranked evaluation snapshots | ELO trend non-regressing across accepted milestones | §2.12 |
| Local proxy fallback when refs unavailable | Local repo may not include George/Albert/Carrie implementations | Use proxy archetypes locally; final sign-off still requires platform reference-bot validation | Local tournament harness using proxy bots + external scrimmage confirmation | Local gates pass and external reference-bot evidence recorded before final promotion | §2.10, §2.12, §8.3 |

---

## Training and Evaluation Protocol

### Scenario Contract

| Scenario | Seed Count | Games | Pass Criteria | Notes |
| --- | --- | --- | --- | --- |
| Baseline self-play stability | 20 | 200 | Zero invalid + zero timeout + zero crash/failure | Sanity and symmetry check |
| Search-generation correctness | 10 | 100 | Explicit search inclusion behaves as designed | Covers `exclude_search=True` default hazard |
| Tri-state search parsing | 10 | 100 | No parse/coercion errors on `True/False/None` | Evidence channel correctness |
| Simulation fidelity parity | 15 | 150 | Rollout adapter matches gameplay semantics | Search scoring/respawn/swap correctness |
| Timeout edge handling | 30 | 300 | No timeout-loss regressions; emergency fallback always triggers | Includes near-floor timing cases |
| Constructor budget robustness | 20 | 200 inits | No constructor timeout failures in configured envelopes | `10s/20s` window awareness |
| Restricted-mode readiness | 20 | 200 | Core behavior valid under resource-limited mode | Local unrestricted parity is not enough |
| Competitive vs baseline pool | 20 | 300 | Positive Elo lift, no reliability regression | Milestone progression gate |
| Grade-alignment local proxy suite | 20 | 300 | Meets proxy thresholds before platform runs | Pre-scrimmage confidence gate |
| Platform reference-bot suite | External | External | Meets George/Albert/Carrie thresholds | Final acceptance gate |

### Mandatory scenario tests (must exist before M3 promotion)

1. Search generation default and explicit inclusion path.
2. Tri-state search tuple parsing.
3. Search scoring/respawn parity in rollout simulation.
4. Timeout edge handling and constructor/play budget windows.
5. Local unrestricted vs restricted readiness checks.
6. Reference-bot gates (or proxy fallback with mandatory platform confirmation).

### Ablation protocol

Toggle and measure effect size independently:

- belief engine on/off
- adaptive search margin on/off
- opponent model on/off
- planner depth tiers
- fallback policy variants

### Regression gates

Reject candidate if any occurs:

- invalid-turn rate above threshold
- timeout-loss rate above threshold
- crash/failure rate above threshold
- negative Elo delta vs previous accepted milestone
- grade-alignment gate regression at corresponding stage

---

## Do / Don’t Checklist

Do:

- Use constructor-provided transition matrix as per-match canonical matrix.
- Explicitly include search actions in candidate generation.
- Parse search event results as tri-state.
- Keep constructor lightweight and fit timeout windows.
- Validate under both unrestricted and restricted runtime modes.
- Keep implementation compliant with assignment environment constraints (no network, no out-of-directory filesystem access, no external non-team code/data).

Don’t:

- Assume local unrestricted defaults match tournament constraints.
- Assume stored `.pkl` values equal runtime matrix values.
- Assume search scoring is handled by `Board.apply_move` in simulations.
- Hardcode initial total time without reading runtime state.
- Introduce dependencies on network calls or off-repo data.
- Promote milestones when reliability gates fail.

---

## Minimal Viable Agent (MVA)

Minimum required capabilities before advanced optimization:

1. Legal move generation with explicit search support.
2. Belief prediction/update with capture reset handling.
3. Time-safe fallback that always returns valid move.
4. Tri-state search telemetry parsing.
5. Basic tactical scoring that outperforms random baseline.
6. Correct package structure with `__init__.py` and relative imports for multi-file agents.

---

## Implementation Execution Contract

This section is normative for implementation handoff. It removes module-boundary ambiguity and defines required outputs per milestone.

### Module Ownership and Required Interfaces

| Module | Ownership | Required Public Interface | Notes |
| --- | --- | --- | --- |
| `agent.py` | Lifecycle orchestration and engine-facing API only | `class PlayerAgent`; `__init__(board, transition_matrix, time_left)`; `play(board, sensor_data, time_left)`; `commentate()` | No belief math or tactical scoring logic should live here beyond wiring and safeguards |
| `belief.py` | Rat posterior state and updates | `class BeliefEngine`; `predict()`; `update(noise, dist, board)`; `reset_after_capture()`; `topk(k)` | Must consume constructor-provided runtime transition matrix and enforce normalization |
| `policy.py` | Candidate generation, scoring, and action selection | `class PolicyEngine`; `generate_candidates(board, belief)`; `score_non_search(board, action, belief)`; `score_search(belief)`; `select_action(board, belief, runtime_state)` | Must implement deterministic ordering, timing guards, and fail-safe order |

### Shared Runtime State Contract

`RuntimeState` (single shared struct/dataclass passed across policy components) must include at least:

- `initial_total_budget`
- rolling normalization stats (`mu_ev`, `sigma_ev`, `mu_t`, `sigma_t`, `eps`)
- opponent profile stats (`observed_turns`, behavior tallies, `behavior_entropy_norm`)
- fallback cache (last validated safe move and timestamp/turn metadata)

### Required Milestone Artifacts (Decision-Complete Outputs)

| Milestone | Required Artifacts |
| --- | --- |
| `M0` | legality/search-inclusion/tri-state tests plus discrepancy-matrix evidence report |
| `M1` | belief correctness report (normalization checks and respawn reset parity checks) |
| `M2` | time-manager profiling report under `strict_240` and `local_360`, plus tactical A/B summary |
| `M3` | adaptation clamp verification report and Elo uplift report vs accepted M2 baseline |
| `M4` | platform evidence pack for George/Albert/Carrie thresholds and Elo trend |

---

## Implementation Milestones

### M0: Correctness Foundation

Deliverables:

- Ground-truth constraints implemented.
- Explicit search action handling.
- Discrepancy matrix items covered by tests.

Acceptance:

- No contradiction with `assignment_spec.md` §2/§3/§5/§9.
- Zero invalid-turn failures in smoke suite.

### M1: Belief and Search Core

Deliverables:

- Posterior tracker with transition + observation updates.
- Search EV integration and reset-aware belief handling.

Acceptance:

- Posterior normalization and stability verified.
- Search precision above random-search baseline.

### M2: Tactical Competitive Core

Deliverables:

- Multi-term tactical scorer.
- Time manager with hard-stop fallback.
- Initial policy constants table integrated.

Acceptance:

- Positive score differential vs baseline pool.
- Timeout loss gate satisfied.

### M3: Adaptive Competitive Upgrade

Deliverables:

- Opponent-aware adaptive weighting.
- Search margin adaptation by game state.

Acceptance:

- Elo lift vs M2 without reliability regression.
- Mandatory scenario tests all green.

### M4: Elite Optional Layer

Deliverables:

- Anytime planner and optional caching/tuning.
- Grade-alignment final acceptance package.

Acceptance:

- Incremental Elo lift vs M3.
- George/Albert/Carrie gates met in platform validation.

---

## Milestone Advancement Gate Table

| From | To | Must-Pass Reliability Gates | Must-Pass Correctness Gates | Must-Pass Performance Gates |
| --- | --- | --- | --- | --- |
| M0 | M1 | Invalid/timeout/crash thresholds all pass under `strict_240` | Search inclusion + tri-state parsing tests pass | Baseline tactical floor beats random/legal baseline |
| M1 | M2 | Reliability thresholds maintained under `strict_240` | Simulation fidelity contract tests pass | Positive score differential trend |
| M2 | M3 | Reliability thresholds maintained under `strict_240` | Timeout-edge + constructor-window tests pass | Positive Elo delta vs M2 baseline |
| M3 | M4 | Reliability thresholds maintained under `strict_240` | Restricted-mode readiness checks pass | Grade-alignment proxy gates pass |
| M4 | Release | Reliability thresholds maintained under `strict_240` | Full discrepancy matrix coverage evidence complete | George/Albert/Carrie thresholds + ELO evidence complete |

---

## Critique Closure Matrix

| Critique | v4 Gap | Patch | Verification | Status |
| --- | --- | --- | --- | --- |
| Time-cap conservatism | Fixed low cap risked under-utilizing available compute budget | Dynamic allocation with phase multipliers/caps plus anti-burn guard and strict-profile promotion gating | Budget formula/property tests + dual-profile (`strict_240`, `local_360`) evaluation runs | Closed |
| Adaptive stacking risk | Raw adaptive adjustments were not bounded by confidence or envelopes | Confidence-weighted adaptation with per-parameter delta clamps and absolute coefficient envelopes | Clamp-invariant tests over long-run simulation logs (`>=10k` turns aggregate) | Closed |
| Non-executable milestones | Milestones lacked module ownership/interfaces/artifact requirements | Added Implementation Execution Contract with ownership, interfaces, RuntimeState schema, and milestone artifacts | Handoff dry-run confirms implementer can proceed without design decisions | Closed |

---

## Validation Checklist

### Ground-truth consistency

- [ ] Constants and scoring tables match `assignment_spec.md`.
- [ ] Time semantics include both assignment and local runtime nuance.
- [ ] Transition perturbation and canonical runtime matrix handling are explicit.

### Engine-contract consistency

- [ ] Search generation default hazard is explicitly mitigated.
- [ ] Tri-state search tuple behavior is explicitly handled.
- [ ] Search scoring location and respawn semantics are explicitly covered.
- [ ] Winner representation and perspective semantics are explicitly covered.

### Contradiction scan

- [ ] No mandatory external infra dependencies.
- [ ] No unsupported convergence or dominance guarantees.
- [ ] No conflict with §9 discrepancy topics.

### Actionability and interpretability

- [ ] Decision policy includes fixed formulas, thresholds, and tie-break order.
- [ ] Matrices use required fixed row schema.
- [ ] Milestone gate table is complete and deterministic.

### Completeness

- [ ] Discrepancy Completeness Matrix has one row per §9 topic.
- [ ] Policy Constants Table, Simulation Fidelity Contract, and Grade Alignment Evaluation Contract are present.
- [ ] MVA and Do/Don’t sections are present.

### Critique Closure

- [ ] Time-cap conservatism closure is explicitly implemented (dynamic allocation + dual-profile gating).
- [ ] Adaptive stacking closure is explicitly implemented (confidence weighting + delta/absolute clamps).
- [ ] Execution ambiguity closure is explicitly implemented (Implementation Execution Contract + artifact requirements).

### Post-Update Re-Audit

- [ ] Ground-truth check: all new assignment/engine claims reference `assignment_spec.md` where relevant.
- [ ] Determinism check: identical state+seed yields identical decision at time/adaptation boundaries.
- [ ] Safety check: allocation never negative and never exceeds anti-burn guard.
- [ ] Stability check: adaptation never breaches clamp envelopes in long-run simulation logs.
- [ ] Actionability check: implementation can proceed directly from documented contracts without unresolved choices.
- [ ] Final audit output records closure status for all three large critiques.

---

## Ground-Truth Alignment Matrix (v3 -> v4)

| High-Risk Topic | v3 Direction | v4 Direction | Status | Source |
| --- | --- | --- | --- | --- |
| §9 discrepancy coverage | Partial high-risk subset | Full one-row-per-topic §9 lock matrix | `Compatible -> Exact` | `assignment_spec.md` §9 |
| Grading alignment | Generic baseline targets | Explicit George/Albert/Carrie gates + ELO linkage | `Compatible -> Exact` | §2.12 |
| Policy determinism | Qualitative strategy and thresholds | Fixed formulas, constants, caps, deterministic tie-break | `Compatible -> Exact` | §10.3, §10.6 + v4 defaults |
| Rollout semantics | Mentions gameplay nuance | Formal simulation fidelity contract with parity tests | `Compatible -> Exact` | §4, §5.4, §9 |
| Operator scaffolding | Absent MVA/Do-Don’t/gating matrix | Restored with milestone advancement gates | `Conflict fixed` | v2 scaffolding + §10 |

---

## Claim-by-Claim Audit Table

| Original Claim (v1-v3 lineage) | Status | v4 Revised Claim | Why Changed | Source |
| --- | --- | --- | --- | --- |
| Local runtime assumptions are sufficient for final readiness | Conflict | Local unrestricted validation is necessary but insufficient; restricted + platform validation required | Prevent tournament-environment mismatch | `assignment_spec.md` §7.4, §7.5, §9 |
| Grade targets can be generic baseline win rates only | Conflict | Final acceptance requires George/Albert/Carrie and ELO-linked evidence | Align with assignment grading language | §2.12 |
| Search rollout semantics can be approximated informally | Conflict | Rollout adapter must satisfy explicit simulation fidelity parity tests | Remove hidden implementation ambiguity | §5.4, §9 |
| Policy thresholds can remain qualitative | Conflict | Time/search/tie-break policy must be fixed and deterministic in this plan | Ensure AI-agent executability | §10.3, §10.6 + v4 defaults |
| v3 tiering and risk framing are useful | Exact | Preserve Baseline/Competitive/Elite layering and reliability-first gating | Keep strong staged structure | v3 + §10 |

---

## Change Ledger (v3 -> v4)

| Change ID | From | What Changed | Why | Status | Source |
| --- | --- | --- | --- | --- | --- |
| V4-01 | v3 | Added full `Discrepancy Completeness Matrix` with one row per §9 topic | Close coverage gaps and enforce complete lock | Added | `assignment_spec.md` §9 |
| V4-02 | v3 | Added `Grade Alignment Evaluation Contract` with George/Albert/Carrie + ELO rows | Align acceptance criteria to assignment grading | Added | §2.12 |
| V4-03 | v3 | Added fixed-schema `Policy Constants Table` with formulas, caps, thresholds, and tie-break determinism | Make policy decision-complete for implementers | Added | §10.3, §10.6 |
| V4-04 | v3 | Added fixed-schema `Simulation Fidelity Contract` | Remove rollout-semantics ambiguity | Added | §4, §5.4, §9 |
| V4-05 | v3 | Added mandatory scenario list with explicit coverage requirements | Ensure required tests are not optional | Added | §10 |
| V4-06 | v3 | Reintroduced `Do/Don’t` checklist | Improve operator clarity and error prevention | Added | v2 scaffolding |
| V4-07 | v3 | Reintroduced `Minimal Viable Agent (MVA)` section | Define minimum capability floor before optimization | Added | v2 scaffolding |
| V4-08 | v3 | Added `Milestone Advancement Gate Table` | Enforce must-pass gates before progression | Added | Milestone governance |
| V4-09 | v3 | Strengthened constructor/restricted-mode readiness language | Address runtime-mode risk explicitly | Added | §7.2, §7.4, §7.5 |
| V4-10 | v3 | Preserved v3 strengths (tiering, risk register logic, reliability-first posture) while adding deterministic contracts | Keep best prior structure and improve executability | Exact/Expanded | v3 lineage |
| V4-11 | v4 | Replaced conservative per-turn max-cap policy with balanced dynamic allocation (phase multipliers, phase caps, anti-burn guard, dual budget profiles) | Improve tactical headroom while preserving strict reliability controls | Added | `assignment_spec.md` §3.2, §5.5, §7.5, §9 |
| V4-12 | v4 | Added bounded opponent adaptation contract (confidence weighting, delta clamps, absolute envelopes, 2-turn cadence) | Prevent unstable coefficient stacking and improve reproducibility | Added | Policy determinism contract |
| V4-13 | v4 | Added `Implementation Execution Contract` with module ownership, required interfaces, shared runtime state contract, and milestone artifact outputs | Make implementation handoff decision-complete for AI agents | Added | Execution readiness |
| V4-14 | v4 | Added `Critique Closure Matrix` and post-update re-audit checklist; aligned all milestone promotion reliability gates to `strict_240` | Close remaining audit gaps and enforce one-profile promotion rule | Added | `assignment_spec.md` §7.5, §9 |

---

## Final Build Order

1. Ship M0 correctness foundation and §9 discrepancy lock tests.
2. Build M1 belief + search EV integration and verify reset semantics.
3. Build M2 tactical core with fixed policy constants and emergency timing.
4. Add M3 adaptive upgrades only after mandatory scenario suite passes.
5. Add M4 elite layer only if reliability and grade-alignment gates remain satisfied.

Execution gate rule:

- Never advance if any reliability gate fails under `strict_240`.
- Never release final candidate without grade-alignment evidence.

Canonical status:

- This document supersedes v3 as the decision-complete, ground-truth-complete planning spec.
- Prior docs remain for traceability only.
