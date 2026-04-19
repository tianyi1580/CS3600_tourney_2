# Final Rat Tracking and Guess Policy

This document defines the final, implementation-ready policy for tracking the rat and deciding when to guess. It replaces ambiguous threshold logic with explicit formulas and a strict horizon switch.

---

## 1) State Estimation (Exact HMM)

Maintain a 64-cell posterior belief over rat location.

### 1.1 Prior / Reset Prior

- Let `T` be the runtime transition matrix passed to the agent.
- Let `e0` be one-hot at `(0,0)` in flattened indexing.
- Cache reset prior:

`b_reset = e0 @ T^1000`

- On game start, set `b = b_reset`.
- On any successful search (self or opponent), immediately set `b = b_reset` and set the post-respawn matrix flag (see §1.4).

Engine verification: `rat.py:127-128` confirms respawn is always at `(0,0)` followed by 1000 moves. This is invariant — the rat never respawns at a random location or point of capture.

### 1.2 Precomputed Matrices

The rat moves **once per game turn** (for both players' turns). Between your consecutive turns, the rat normally moves **twice**: once during the opponent's turn (unobserved) and once during your turn (observed). Precompute and cache in `__init__`:

- `T` — single-step transition.
- `T2 = T @ T` — double-step transition.

### 1.3 Per-Turn Forward Update

On each of your turns with sensor `(noise_t, dist_est_t)`:

#### 1.3.1 Standard case (no opponent miss to integrate):

1. Select prediction matrix per §1.4 rules.

`b_pred(i) = sum_j b_prev(j) * T_selected(j, i)`

2. Emission:

`L(i) = P(noise_t | floor_type(i, current_board)) * P(dist_est_t | manhattan(i, worker_loc_t))`

3. Correction and normalization:

`b_new(i) = alpha * L(i) * b_pred(i)` where `alpha` normalizes sum to 1.

#### 1.3.2 Split-step case (opponent missed at cell g since our last turn):

When the opponent searched at cell `g` and missed, the negative information ("rat was NOT at g") applies at the **opponent's** time step, not ours. Naively zeroing `g` after propagating with `T2` is wrong: it says "rat is not at g NOW", when the truth is "rat was not at g ONE step ago". The rat could have moved into g during the step between the opponent's turn and ours.

Correct procedure — split the `T2` propagation around the evidence:

1. Propagate one step (opponent's unobserved rat move): `b_inter = b_prev @ T`
2. Apply negative info at the correct time: `b_inter(g) = 0`, renormalize.
3. Propagate one more step (our observed rat move): `b_pred = b_inter @ T`
4. Apply sensor emissions to `b_pred` to get `b_new`.

This split applies ONLY when the opponent missed. In all other cases (no opponent search, opponent hit, self miss, self hit), use the standard path from §1.3.1.

Note on self misses: When YOU search and miss at cell g, the negative info applies at YOUR time step (the current posterior). Zeroing g on the current belief is correct — no split needed.

### 1.4 Prediction Matrix Selection (Handles Game Start AND Respawn)

The number of untracked rat steps between your belief snapshot and your observation depends on **who acted last** relative to the rat's reset point. This applies identically to game start and every post-capture respawn.

**Rule**: After a belief reset to `b_reset` (game start or capture), count how many `rat.move()` calls occur before your next observation:

- **Opponent caught the rat (or you are Player A on turn 1):** Their turn ends → rat respawns (1000 steps) → your turn begins → `rat.move()` once → you observe. Total untracked moves since reset: **1**. Use `T`.
- **You caught the rat (or you are Player B on turn 1):** Your turn ends → rat respawns (1000 steps) → opponent's turn → `rat.move()` once (unobserved by you) → your turn → `rat.move()` once → you observe. Total untracked moves since reset: **2**. Use `T2`.

**Implementation**: maintain a flag `use_single_step`:
- Initialize `use_single_step = True` if Player A, `False` if Player B.
- On **opponent** successful search (detected via `board.opponent_search`): set `use_single_step = True`.
- On **own** successful search: set `use_single_step = False`.
- On opponent miss: use the split-step procedure from §1.3.2 instead of the flag-selected matrix.
- After prediction: reset `use_single_step = False` (subsequent turns use `T2` until next reset).

### 1.5 Required Edge Handling

- Recompute `P(noise | floor_type)` every turn from current board floors.
- Distance model must include clipping:
  - reported distance is `max(0, true_dist + offset)` for offsets `{-1, 0, +1, +2}` with probs `{0.12, 0.70, 0.12, 0.06}`.
  - Therefore, when `true_dist = 0`, `P(reported=0) = 0.82`.
  - When `true_dist = 1`, `P(reported=0) = 0.12` (from offset -1 clipped to 0).

### 1.6 Search Feedback Integration

- **Opponent miss at cell g**: Do NOT zero g immediately. Instead, set a pending flag `(opp_miss_cell = g)`. The zeroing is applied mid-propagation in §1.3.2.
- **Self miss at cell g**: set `b(g)=0`, renormalize. This is correct because the negative info is at the current time step.
- **Opponent hit**: reset to `b_reset`, set `use_single_step = True`.
- **Self hit**: reset to `b_reset`, set `use_single_step = False`.

---

## 2) Definitions Used by Policy

- `p1`: largest posterior cell probability.
- `g*`: argmax cell for `p1`.
- `r_me`: my turns remaining.
- `r_opp`: opponent turns remaining (computed from actual turn parity).
- `S_me`, `S_opp`: current scores.
- `Q_best_non`: immediate point gain of best legal non-search action this turn (Prime = 1, Carpet(k) = carpet_table[k], Plain = 0).
- `M_non(board, k)`: max non-search points achievable over the next `k` turns from `board`, computed by greedy rollout (see §4.2).
- `E_opp_final`: opponent projected final score, computed by greedy rollout in endgame (see §4.1).

---

## 3) Standard Policy (Strictly for r_me > 3)

When `r_me > 3`, maximize expected points.

### 3.1 Guess Gate

Guess at `g*` iff:

`6*p1 - 2 >= Q_best_non + margin`

Where `margin = 0.5` (information retention margin).

If the condition fails, take best non-search action.

**Rationale for margin**: At the exact breakeven (`6*p1 - 2 = Q_best_non`), the guaranteed board action is strictly preferred over the uncertain guess because: (a) board points are deterministic while the guess is a gamble, and (b) one additional observation before guessing has positive expected information value, even if the magnitude is uncertain (the posterior may sharpen or diffuse depending on the noise realization and rat movement). The margin ensures the guess is materially better, not just marginally equal. A margin of 0.5 means:

- When priming is available (`Q_best_non = 1.0`): requires `p1 >= 0.583`.
- When only plain steps available (`Q_best_non = 0`): requires `p1 >= 0.417`.
- When a carpet is available (`Q_best_non = 4.0` for length-3): requires `p1 >= 1.08` — never triggers, correctly prioritizing the carpet.

There is no separate hard floor on `p1`. The dynamic threshold `(Q_best_non + margin + 2) / 6` adapts to the board situation automatically.

### 3.2 Notes

- No opponent-denial term is used.
- No extra risk padding term is used in standard mode.
- Decision remains in point units and directly comparable.

---

## 4) Endgame Policy (Strictly for r_me <= 3)

When `r_me <= 3`, objective switches from expected points to probability of winning.

### 4.1 Opponent Exact Projection

Use a greedy k-ply rollout to project opponent's non-search score, mirroring §4.2. 

To simulate opponent moves: `board.get_copy()` → `reverse_perspective()` → now `player_worker` is the opponent → `forecast_move()` and `get_valid_moves()` work correctly.

`E_opp_final = S_opp + M_non(opponent_board_copy, r_opp)`

Do not use a heuristic proxy — a capped proxy like `V_opp_proxy ∈ [0.5, 4.0]` will miss large one-shot actions (e.g., a 21-point carpet roll) and underestimate the opponent's finish, preventing the must-guess gate from triggering when it should.

### 4.2 Self Non-Search Future Value: Greedy k-Ply Rollout

Compute `M_non(board, k)` by a deterministic depth-k greedy rollout over legal non-search moves. This is exact for the board state and avoids the heuristic explosion of multiplying a one-shot payload by `k` (see below).

**Algorithm**:
```
function M_non(board, k):
    if k == 0: return 0
    best = 0
    for each valid non-search move m on board:
        gain = immediate_points(m)     // Prime=1, Carpet(n)=carpet_table[n], Plain=0
        board_after = board.forecast_move(m)
        best = max(best, gain + M_non(board_after, k - 1))
    return best
```

**Why not a heuristic proxy**: A proxy like `V_self * k` breaks on consumable actions. Example: with k=3 and a length-7 carpet available, the proxy projects `3 × 21 = 63` points — impossible because the carpet consumes its primed squares. The actual rollout yields ~23 (carpet on turn 1, two primes on turns 2-3). The inflated proxy permanently disables the must-guess desperation gate.

**Performance**: With k ≤ 3 and typical branching factor ~4-8 non-search moves, the search space is at most ~512 nodes. This takes microseconds.

### 4.3 Must-Guess Override

If even best non-search catch-up line cannot beat projected opponent finish:

`S_me + M_non(my_board, r_me) <= E_opp_final`

then force search at `g*` (must-guess state).

### 4.4 Win-Probability Action Selection

If must-guess condition does not trigger, choose action maximizing approximated `P(win)`.

For search now at `g*` with hit prob `p1`, evaluate:

`Pwin(search) = p1 * I(S_me + 4 + M_non(my_board_after_search, r_me - 1) > E_opp_final) + (1-p1) * I(S_me - 2 + M_non(my_board, r_me - 1) > E_opp_final)`

For non-search action `a` with immediate expected gain `gain(a)`:

`Pwin(a) = I(S_me + gain(a) + M_non(board_after_a, r_me - 1) > E_opp_final)`

Where:

- `I(.)` is indicator 1/0.
- `E_opp_final = S_opp + M_non(opponent_board, r_opp)` (exact rollout, not proxy).
- Use strict `>` unless tournament tie semantics explicitly reward ties.

Select action with maximum estimated `Pwin`.

---

## 5) V_opp_proxy (Standard Mode Only)

In standard mode (`r_me > 3`), `V_opp_proxy` is not used in the guess gate. It is only relevant if future enhancements add opponent-aware scoring features. Retained as a lightweight heuristic for any such extensions:

- near-carpet-ready state -> higher value (up toward ~3.5)
- primarily priming / low setup -> around ~1.0
- clamp to stable range `[0.5, 4.0]`

In endgame mode (`r_me <= 3`), `V_opp_proxy` is NOT used — §4.1 uses the exact greedy rollout instead.

---

## 6) Final Non-Negotiable Constraints

1. Exact HMM update each turn.
2. Dynamic floor-conditioned noise emissions each turn.
3. Correct distance clipping at zero boundary (`P(d_hat=0 | d=0)=0.82`).
4. **Prediction matrix selection based on post-reset rat step count**: `T` when 1 untracked step (opponent caught rat, or Player A turn 1); `T2` when 2 untracked steps (self caught rat, or Player B turn 1, or normal play).
5. **Split-step propagation on opponent miss**: propagate T, zero out missed cell, propagate T again — NOT zero-after-T².
6. Post-respawn matrix flag updated on every capture event (not just game start).
7. Standard mode only for `r_me > 3`.
8. Endgame mode only for `r_me <= 3` (strict boundary).
9. Guess gate uses `6*p1 - 2 >= Q_best_non + 0.5` — no separate hard floor on `p1`.
10. No opponent-denial modifiers in guess threshold.
11. `M_non(board, k)` computed by exact greedy k-ply rollout for BOTH self and opponent projections.
12. Rat respawn is always at `(0,0)` per `rat.py:127-128`. `b_reset` cache is valid across all respawns.

This policy is the final tournament-ready blueprint.
