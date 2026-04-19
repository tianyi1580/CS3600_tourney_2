# Yolanda Prime v3: Comprehensive Enhancement Plan

## 0. Intent and scope

A new package `3600-agents/yolanda_prime_v3/` that preserves `yolanda_prime_v2` untouched (so the ongoing CMA-ES run on `data/hyperopt/yolanda_prime_v2/pace_run/` continues). v3 reuses v2's belief engine, weight loading, build fingerprint, runtime-state scaffolding, and the hyperopt workflow shape, but replaces the three pieces that are actually bottlenecking strength:

- `strategy/policy.py` (2458 lines of additive heuristics) → a thin orchestrator over (a) a new bitboard alpha-beta search, (b) a Voronoi/territory evaluator, (c) a multi-turn carpet planner.
- `strategy/lookahead.py` (shallow minimax on `Board.forecast_move`) → `strategy/search/alphabeta.py` (bitboard, iterative deepening, transposition table, PVS, quiescence).
- `strategy/board_analysis.py` (BFS over `Board`) → `strategy/territory.py` (Voronoi + carpet potential over bitboards).

The leaf eval combines five legible terms (instead of ~30 overlapping ones) so CMA-ES has clean gradients:
**Eval = α·(score_delta) + β·(territory_value_delta) + γ·(chain_potential_delta) + δ·(mobility_delta) + ε·(belief_info_value)**.

## 1. Module layout

```
3600-agents/yolanda_prime_v3/
  agent.py                          # PlayerAgent -> Orchestrator
  infra/
    bitboard.py                     # State, masks, Zobrist, move encoding
    time_manager.py                 # New aggressive budgeter (see §4)
    weights.py                      # Spec list + load (port from v2)
    runtime_state.py                # Ported/slimmed from v2
    build_fingerprint.py            # Reused verbatim
  tracking/
    belief.py                       # Port from v2 + entropy/info-gain helpers
    opponent_observation.py         # Ported from v2
  strategy/
    territory.py                    # Voronoi + carpet-potential maps (§2)
    carpet_planner.py               # Multi-turn chained-carpet DP (§3)
    search/
      alphabeta.py                  # Iterative deepening alpha-beta + TT + PVS (§5)
      ordering.py                   # Killer, history, SEE-like ordering
      quiescence.py                 # Extend until no CARPET available (§5.4)
    leaf_eval.py                    # Five-term evaluator (§6)
    search_policy.py                # Search-vs-move decision + denial equity (§7)
    info_foraging.py                # Cardinal-sweep bias under high entropy (§8)
    orchestrator.py                 # select_action pipeline (§9)
  weights.json                      # Seed weights from v2 where analogous, new ones defaulted
```

## 2. Voronoi territory engine (fixes issue #1: spatial awareness)

### 2.1 Dual BFS ownership
For every non-blocked cell `c`, compute `d_us(c)` and `d_opp(c)` — shortest path via **plain-walkable** cells (SPACE ∪ CARPET, excluding PRIMED and occupied) from each worker. Edge weights treat CARPET traversal as cost 1 (no score gain) and entering a PRIMED cell as invalid for the BFS (primed-step priming is captured by a separate prime-potential score below).

Ownership:
```
own(c) =  +1 if d_us(c) <  d_opp(c) - 1   # Safe
           -1 if d_opp(c) < d_us(c) - 1    # Dead
            0 otherwise                    # Contested (tempo-dependent)
```
The ±1 margin is the *tempo buffer* — a one-move race in the contested zone is treated as a 50/50 expected claim.

### 2.2 Carpet-potential map
For each cell `c`, compute `prime_potential(c)` = the maximum carpet yield achievable if **`c` is the entry cell of a contiguous SPACE ray primed and then carpeted from c** (ignoring adversary for now):
```
prime_potential(c) = max_d  CARPET_POINTS_TABLE[ min(ray_space_len(c,d), 7) ]
```
where `ray_space_len(c,d)` counts contiguous SPACE cells along direction d. This is a static 64-entry lookup per turn, O(64·4).

### 2.3 Territory value
```
territory_value_us =  Σ over SPACE c:  own(c) * prime_potential(c)  * tempo_weight(c)
tempo_weight(c)    =  1.0                  if own(c) ≠ 0
                      0.5 * sign(d_opp(c) - d_us(c))  otherwise  # contested
```
This is THE primary fix for map control. Because the value scales with the best carpet achievable *from* the cell if we claim it, the bot will gravitate toward — and defend — open regions that enable L5/L6/L7 rolls.

### 2.4 Integration points
- Added directly to `leaf_eval.py` as the `β·(territory_value_delta)` term (after-minus-before).
- Gives a positional-prime reward: a `PRIME` action that *keeps us the Voronoi owner* of a long open ray gets the full ray value; one that lets the opponent win the race on an adjacent ray gets penalized automatically by the subtraction.
- Recomputed at every search node (cheap: two BFS on 64 cells + a 64-entry ray scan, ~80µs each).

## 3. Multi-turn chained-carpet planner (fixes issue #2)

### 3.1 Motivation
When the Voronoi map says we safely own a region, the decision "carpet L3 now vs. extend to L5" is a small DP, not a single-turn heuristic. v2's `_can_extend_chain` only looks 1 step.

### 3.2 Algorithm (`strategy/carpet_planner.py`)
Let `S` = the set of SPACE cells we own in Voronoi with `d_opp > d_us + 2` (safe margin). Define an ACTION as a pair (prime-to-cell, carpet-roll). A **build sequence** is an ordered list of primes on cells in a straight line terminated by one carpet roll.

Compute, for each straight ray through `S` touching our worker's reachable set:
```
plan_value(ray, T)  # T = safe-turn budget until opponent expected to arrive
  = max over k in [2..min(len(ray), 7)]:
      k - 1    # k-1 primes needed (we prime on departure)
      + 1      # 1 carpet roll
      ≤ T
      -> CARPET_POINTS_TABLE[k] + (k-1)*1  (prime points we earn building)
      - approach_cost(ray_start)           # steps to reach ray start
```
Best plan = arg-max over all rays. Approach cost and T-budget are derived from the Voronoi map: `T_safe = d_opp(ray_end) - d_us(ray_start) - 1`.

The planner returns a concrete next move (the first action of the best plan) as a *preferred candidate* that is injected into the search root with a +planner_bias heuristic bonus. The alpha-beta search still validates the plan against opponent responses; if the opponent can disrupt, the search will find the refutation and pick something else.

### 3.3 Chained carpets across turns
If `T_safe ≥ 3`, the planner also considers building L6/L7 chains via two-axis priming (prime 4 cells, then carpet L4 while being able to extend perpendicular). The chain-with-elbow case is evaluated by trying both orders and keeping the higher-yield one.

### 3.4 When to invoke
Only computed at the root (not in search nodes) because its payoff is move-ordering and a leaf-eval bonus, not an inner-loop decision. Cost: <1 ms.

## 4. Time manager v3 — actually spend the budget (issue #3)

### 4.1 Problem
v2 caps phase budgets at 8/6/3s but the Python lookahead completes in ~20-50ms. The bot used <2s in a 240s match.

### 4.2 New allocator (`infra/time_manager.py`)
```
base  = (time_left - reserve) / turns_left
alloc = base * phase_mult(turn) * complexity_mult(board_state)
```
Key changes:
- `reserve` is **static 5s end-of-game safety**, not per-turn.
- `phase_mult`: opening 1.8, mid 1.6, late 1.2 (softer decay — we want to think hard in late turns too, because a carpet mistake is larger).
- `complexity_mult ∈ [0.7, 1.6]` derived from:
  - root move count (more choices → more time)
  - top-2 move gap at depth 2 after iterative deepening root completion (close race → more time)
  - opponent in contested zone (Voronoi overlap ≥3 cells → more time)
  - belief entropy near search-gate threshold (decision-boundary turn → more time)
- `phase_cap` removed; only a global `min(alloc, 0.25 * (time_left - reserve))` guard prevents single-turn blowup.

### 4.3 Iterative deepening hooks
`alphabeta.search` receives a **soft deadline** (start + alloc) and a **hard deadline** (start + alloc*1.15). ID completes the current depth if within hard deadline, even if soft is exceeded, to never return a partial-ply result. This gives 4-10s of real search per contested turn, vs v2's ~30ms.

## 5. Bitboard alpha-beta engine (issue #3 + strategic depth)

### 5.1 State representation (`infra/bitboard.py`)
```python
@dataclass(slots=True, frozen=True)
class BBState:
    space: int       # 64-bit mask
    primed: int
    carpet: int
    blocked: int
    us: int          # flat idx 0..63
    opp: int
    us_score: int
    opp_score: int
    us_turns: int
    opp_turns: int
    us_to_move: bool
```
All transitions return a new BBState (slots = cheap). Precomputed: `ADJ[64]` (4-neighbor mask), `RAY[64][4]` (bitmask of cells along each direction to edge), `RAY_FIRST_STOP[64][4]` ordered neighbor indices for fast iteration.

### 5.2 Move generation (bitwise)
- `plain[loc]  = ADJ[loc] & ~blocked & ~primed & ~(1<<us) & ~(1<<opp)`
- `prime[loc]  = plain[loc]` if `(1<<loc) & space` (can prime only from SPACE)
- `carpet` per direction `d`: walk `RAY[loc][d]` while bit is in primed and not occupied; emit every legal length k.

Legal-move enumeration cost: ~0.5µs per state (vs. v2's `board.get_valid_moves` ≈ 30-50µs). This alone is 100× speedup.

### 5.3 Zobrist + transposition table
- 64-bit random keys for each cell-type-at-cell + worker positions + side-to-move (total ~800 constants, seeded from `hash(transition_matrix.tobytes())` so keys are identical across self-play but different across games).
- TT is a `dict[int, TTEntry]` bounded at **80 000 entries** (well under 1.5 GB RLIMIT_RSS — each entry ~200 B → 16 MB).
- LRU eviction by tracking insertion order in a bounded deque; on overflow pop oldest.
- TTEntry carries `(depth, flag ∈ {EXACT, LOWER, UPPER}, value, best_move, generation)`.
- TT cleared **between turns** as a safety net and to maintain generation freshness.

### 5.4 Search algorithm
Principal Variation Search (PVS) with:
- **Iterative deepening** from depth 1 to ∞ (practical cap 12), break on soft deadline.
- **Aspiration windows** for d ≥ 4: start with `[best_prev - 50, best_prev + 50]`, widen on fail.
- **Move ordering** (`strategy/search/ordering.py`):
  1. TT best move for this position, if present.
  2. Carpets sorted by carpet-points desc (these are "captures").
  3. Primes sorted by (chain-alignment-behind + ahead-open-space).
  4. Plain moves toward highest-carpet-potential territory per Voronoi.
  5. Killer moves at this ply (2 per ply).
  6. History heuristic score.
- **Quiescence** (`quiescence.py`): at depth ≤ 0, continue searching **only CARPET moves with roll_length ≥ 3**; stop when the side to move has no carpet available. This resolves the horizon effect where depth-N search misses a carpet-now-vs-next-turn trade.
- **Late move reductions**: for non-carpet, non-TT moves at depth ≥ 3 and move index ≥ 4, search at depth-2 with a narrow window; re-search full depth if it raises alpha.
- **Null-move pruning DISABLED** — this game's zero-sum property with asymmetric scoring (prime +1 to the primer only, carpet to the roller only) means passing is genuinely worse than any move; null-move's theoretical assumption doesn't hold cleanly. Re-evaluate later if empirically beneficial.
- **SEARCH moves are NOT expanded in the tree** — they are evaluated by `search_policy.py` once per turn at the root (§7) and compared against the tree's best non-search line.

### 5.5 Chance-node modelling for rat (optional, depth-dependent)
The game's only stochasticity from the agent's perspective is the sensor. Because search-move scoring is handled outside the tree, inside the tree the game is **deterministic**. So pure minimax (not expectiminimax) is correct. This is a simplification win over what the `docs/assignment_spec.md` Appendix suggests — correct for our specific decomposition.

## 6. Leaf evaluator (`strategy/leaf_eval.py`)

Replaces `Lookahead.static_eval_differential` (which only looks at 4 rays per worker) with a five-term function:

```
eval(state)
  = α · (us_score - opp_score)
  + β · (territory_value_us - territory_value_opp)                # §2
  + γ · (chain_potential_us - chain_potential_opp)                # best 1-turn carpet each side
  + δ · (mobility_us - mobility_opp)                              # popcount of plain moves
  + ε · belief_info_bonus                                         # §8
```

- `chain_potential` = max over directions of `CARPET_POINTS_TABLE[k]` where k is the adjacent primed-chain length that would be rollable *this turn*. Already available in v2, bitboard-native here.
- Bonus scalar `ω_threat` penalty if the opponent has an immediate carpet response after our move ≥ 6 points and we don't have a matching one. (Replaces the 20+ bespoke penalties in v2.)
- Concrete defaults: `α=1.0, β=0.35, γ=0.25, δ=0.05, ε=0.12, ω_threat=0.6`. Surfaced to `weights.json` for CMA-ES.

## 7. Search (rat-guess) policy with denial equity (`strategy/search_policy.py`)

Replaces the scalar `_search_gate`. Once per turn at the root:

### 7.1 Compute three quantities
- `ev_search` = `6·p_max - 2`, where `p_max` = our belief peak.
- `ev_best_move` = root alpha-beta value at the deepest completed depth.
- `denial_equity` = `4 · P(opp_guess_hit_this_turn)` where `P(opp_guess_hit)` is estimated as:
  - `P(opp knows p_max cell) ≈ min(1.0, opp_belief_peak_proxy)` where the proxy is a shadow HMM we maintain for the opponent: same transition matrix, same sensor model, but using their worker position (known) and a uniform prior updated at each of their turns with a sensor draw we can't see. We bound this by assuming their posterior peak is at least `0.9 · p_max - 0.1` after symmetric information exposure.
  - `P(opp_guess_hit) = opp_peak_prob · [L1(opp_loc, belief_peak_cell) ≤ 2]` — they can only guess where they're "near" based on the sensor-geometry of the L1 diamonds.

### 7.2 Decision rule
```
fire_search  if  ev_search + λ_denial · denial_equity  >  ev_best_move + margin(phase, lead, recovery)
```
- `λ_denial ∈ [0.5, 1.5]` — CMA-ES tunable.
- `margin` keeps v2's existing phase/lead/hysteresis logic (it is reasonable) but strictly subtracts denial_equity from `ev_best_move` side, not from both.

### 7.3 Multi-turn search lookahead
Keep v2's `_endgame_search_pwin` for the last 3 turns. Extend it to 5 turns but with a belief-miss-refinement cache so it stays <10 ms.

## 8. Information-gain foraging (`strategy/info_foraging.py`)

### 8.1 Cardinal-sweep bias under high entropy
Compute belief entropy `H = -Σ p_i log p_i`. Normalized `H_norm = H / log(64)`.

For each candidate move that *is a PLAIN or PRIME step*, compute expected posterior entropy reduction under the sensor model at the new worker position:
```
E[H_after | move] = Σ_rat_cell P(rat=cell)
                    Σ_noise Σ_dist P(noise|cell) P(dist|L1(new_pos, cell))
                    · H(posterior_after_obs)
```
Full enumeration is 64 × 3 × 20 = 3840 inner iterations per move; with vectorized numpy we batch it to <2ms for up to 8 candidate moves. The key insight (Strategy 4 in `next.md`): moves that cross L1 iso-distance contours yield highest entropy reduction. Cardinal straight-line steps naturally do this, so the math will reward them without hard-coding "prefer cardinals" — with a **safety patch** for corner-blocked-mask edges where the rat may be under a wall.

### 8.2 Plug-in
Add term `ε · belief_info_bonus` to the leaf evaluator (§6), **active only for plain/prime transitions where `H_norm > 0.75`**. Gated so it doesn't hijack late-game cashout.

## 9. Orchestrator pipeline (`strategy/orchestrator.py`)

Per turn:
1. Apply search-channel belief updates (ported from v2's `apply_search_channels`).
2. Run belief `predict` + `update` with sensor_data.
3. Build `BBState` from `Board`.
4. Compute Voronoi + carpet-potential maps (§2), territory values.
5. Run `carpet_planner.plan(bbstate, territory)` to get a preferred root move (§3).
6. Compute `ev_search` via `search_policy.compute_ev_search` (§7).
7. Call `alphabeta.iterative_deepening(bbstate, deadline)` (§5); root returns `(best_move, ev_best_move, pv)`.
8. Apply `search_policy.decide(ev_search, ev_best_move, denial_equity, phase, state)` → returns a Move (search or the alpha-beta best).
9. Persist runtime state, return Move.

Failover: any exception anywhere falls through to `board.get_valid_moves(exclude_search=True)[0]` — unchanged from v2.

## 10. Reuse, migration, and tuning

### 10.1 Reused verbatim (or light port) from v2
- `tracking/belief.py` → `yolanda_prime_v3/tracking/belief.py` (add `entropy()` helper).
- `tracking/opponent_observation.py` → ported as-is.
- `infra/build_fingerprint.py`, `infra/weights.py` (spec list) → ported; new `_SPECS` are **additive** (α,β,γ,δ,ε,ω_threat, λ_denial, planner_bias, territory_opp_margin, time multipliers) and old A/B/C/D spec tiers remain so the CMA-ES workflow doesn't need structural changes.
- `workflows/yp2_hyperopt.py` → copy to `workflows/yp3_hyperopt.py` with a one-line agent name change, so the optimizer hits the new leaf eval coefficients.

### 10.2 Staged hyperparameter optimization
Per your guidance ("optimize hyperparameters first before going deeper"):
1. **Stage 1 (fixed-depth)**: lock alpha-beta at depth 4, tune leaf-eval weights (α,β,γ,δ,ε,ω_threat) with CMA-ES until convergence.
2. **Stage 2 (time-aware)**: unlock iterative deepening, tune time-manager multipliers and `complexity_mult` knobs.
3. **Stage 3 (search policy)**: tune `λ_denial` and search gate margins with frozen leaf weights.
4. **Stage 4 (interaction)**: fine-tune all A-tier weights together with a smaller CMA-ES sigma.

Target: each stage runs on PACE with ≥500 games per candidate.

### 10.3 Seeding
`weights.json` is initialized with v2's `a/b/c/d/f/g` mapped to `α/δ/γ/…` approximately, so the stage-1 optimizer starts in a known-good region of the space.

## 11. Risk register and mitigations

- **Bitboard correctness bug** → ship a golden-file test: run v2 and v3 on 50 identical seeds with depth-2 search + deterministic tie-break; assert agreement on move legality set at each turn.
- **TT memory leak** → bounded dict + per-turn clear; add `sys.getsizeof` assertion in debug mode.
- **Deeper search over-fits to PACE bots** → include reference bots Albert/Carrie-like (we only have Yolanda variants) in the CMA-ES evaluation pool across all four stages.
- **Quiescence blow-up** → hard cap qsearch depth at 6 extra plies; empirically rare that carpet-chase goes deeper.
- **Voronoi misclassification near blocked corners** → treat worker-reachable cells only; uncategorized cells get `own = 0` weight.

## 12. Success criteria

- Depth achieved in mid-game with 6s budget: ≥ 8 (measured by TT stats per turn).
- Per-turn wall-clock: opening 5-8s, mid 6-8s, late 2-4s; total per match 180-220s used out of 240s.
- Head-to-head vs v2_baseline: ≥ 60% win rate, Elo delta ≥ +70 over ≥500 games.
- Vs `yolanda_prime_v1_2Test`: break 50% (currently 47%).
- Search precision: ≥ 0.60 (up from ~0.53 in v2), driven by denial-equity gating fewer speculative searches.

