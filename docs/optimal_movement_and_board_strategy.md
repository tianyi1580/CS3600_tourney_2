# Optimal Movement & Board Decision Strategy

> **Scope**: All movement and board decisions OUTSIDE of rat tracking/guessing.
> Rat belief updates, search EV, guess gates, and endgame search policy are defined in
> [`final_rat_tracking_and_guess_policy.md`](./final_rat_tracking_and_guess_policy.md) and are NOT duplicated here.

---

## 0) Design Philosophy

The board game is a **40-turn resource-conversion race**. Raw materials (empty squares) are converted into intermediates (primed squares) then into final products (carpet runs). Every turn spent on a plain step, a bad prime, or a short carpet is a turn NOT spent on a 10–21 point carpet roll or a +4 rat catch. The optimal agent:

1. **Manufactures long carpet chains** (length ≥ 5) as its primary scoring engine.
2. **Primes efficiently** — every prime should contribute to a future carpet of length ≥ 3, ideally ≥ 5.
3. **Minimises wasted turns** — plain steps that don't reposition toward a carpet-laying plan are the worst action.
4. **Denies the opponent** only when the denial cost is lower than the scoring opportunity cost.
5. **Never self-traps** — entering a position with ≤ 1 exit is almost always a losing move.

### Point Economics Reference

The "Total yield" column includes the prime step points (+1 each) earned during chain setup, since every prime turn is itself a scoring action. This is the correct basis for comparing against rat search EV.

| Sequence | Setup turns | Carpet pts | Total yield | Pts/turn (total) | Verdict |
|----------|-------------|------------|-------------|------------------|---------|
| Plain step | 0 | 0 | 0 | 0.0 | Waste unless repositioning |
| Prime step (standalone) | 1 | — | +1 | 1.0 | Acceptable building block |
| 1 prime → Carpet 1 | 1 | −1 | 0 | 0.0 | **Never — worse than priming alone** |
| 2 primes → Carpet 2 | 2 | +2 | 4 | 1.33 | Marginal; only under time pressure |
| 3 primes → Carpet 3 | 3 | +4 | 7 | 1.75 | Acceptable |
| 4 primes → Carpet 4 | 4 | +6 | 10 | 2.0 | Good |
| 5 primes → Carpet 5 | 5 | +10 | 15 | **2.5** | **Very good — primary target** |
| 6 primes → Carpet 6 | 6 | +15 | 21 | **3.0** | **Excellent** |
| 7 primes → Carpet 7 | 7 | +21 | 28 | **3.5** | **Maximum (opportunistic)** |
| Rat catch | 0 | — | +4 | 4.0 (if high-conf) | Best per-turn when belief strong |
| Rat miss | 0 | — | −2 | −2.0 | Devastating |

**Key insight**: A 5-prime + 1-carpet sequence (6 turns) nets 5 + 10 = **15 points** (2.5/turn). A 7-prime + 1-carpet sequence (8 turns) nets 7 + 21 = **28 points** (3.5/turn). These are competitive with all but the highest-confidence rat catches. The table above is the correct basis for opportunity cost calculations — never compare carpet-only payout against search EV without including the prime points earned during setup.

---

## 1) Game Phase Strategy

The 40-turn game is split into three strategic phases. Phase boundaries determine how aggressively to prime vs. carpet vs. reposition.

### 1.1 Opening (Turns 1–12): Land Grab & Infrastructure

**Objective**: Lay down contiguous prime chains in the most valuable board regions.

**Initial board state**: The board starts with ZERO primed or carpeted squares. Only blocked corner rectangles and empty space exist. Both players spawn in the center 4×4. All scoring infrastructure must be built from scratch.

**Priorities (in order)**:
1. **Prime aggressively** in straight lines. Every prime step earns +1 and builds infrastructure.
2. **Claim central corridors first**. The center 4×4 region has the highest connectivity and the most directions to extend chains.
3. **Prefer cardinal-aligned runs** — prime in a straight line (same direction) to build a single long chain rather than an L-shape that wastes turns changing direction.
4. **Avoid the opponent's prime lanes**. If the opponent is priming a row/column, build in a perpendicular corridor rather than competing for the same line.
5. **Never carpet in the opening**. No chains exist yet; you must build them first.

**Anti-patterns**:
- ❌ Random walk priming (changes direction every turn → no long chains).
- ❌ Priming in corners where blocked squares limit chain extension.
- ❌ Priming squares that are isolated from any possible carpet run direction.
- ❌ Plain steps that don't reposition toward a prime-able corridor.

**Opening Prime Placement Heuristic**:
For each candidate prime-step direction, score by:
```
prime_value(dir) = chain_length_if_I_continue(dir) + 0.5 * perpendicular_extension_potential
```
Always prime toward a direction where you can sustain at least 3 more consecutive primes without hitting a wall, blocked cell, or the opponent.

### 1.2 Mid-Game (Turns 13–30): Chain Completion & First Carpets

**Objective**: Complete prime chains and execute carpet rolls for maximum payoff.

**Priorities (in order)**:
1. **Complete chains to length ≥ 5** before carpeting. Adding one more prime turn to go from length 4 (carpet = 6 pts) to length 5 (carpet = 10 pts) costs 1 turn and gains 4 net points — always worth it.
2. **Carpet the longest available chain first**. If multiple chains are ready, roll the longest one. After rolling, the destination square becomes a valid position to begin a new prime chain.
3. **Reposition for the next chain** if no chain ≥ 3 is adjacent. A plain step that puts you adjacent to a cappable chain is better than a wasted prime.
4. **Look for "chain merge" opportunities** — if two separate chains share a gap, filling that gap with a prime can create one long chain worth far more than two short ones.
5. **Begin evaluating rat guess opportunities** (see rat policy doc) — mid-game is when belief often peaks.

**Carpeting Decision Rule**:
```
Should I carpet now? Only if:
  1. Adjacent chain length k >= 3, AND
  2. No single additional prime turn would extend k by 1+ AND
     increase carpet_table[k+1] - carpet_table[k] > 1, OR
  3. I'm being denied access to the chain extension by the opponent, OR
  4. I need the carpet points NOW due to score pressure (see §5).
```

**Anti-patterns**:
- ❌ Carpeting a length-2 chain (+2 pts − 2 primes = 0 net). Almost never correct.
- ❌ Carpeting a length-4 chain when one more prime would make it length-5 (+4 net points for 1 turn).
- ❌ Priming aimlessly when a length ≥ 5 chain is sitting uncarpeted.

### 1.3 Late Game (Turns 31–40): Point Maximization & Desperation

**Objective**: Convert ALL remaining infrastructure into points. No more building for the future.

**Priorities (in order)**:
1. **Carpet every available chain ≥ 3 immediately**. There is no "later" to wait for.
2. **Carpet chains of length 2** only if no better option exists (still +2 pts vs +1 from a prime).
3. **Prime only if it directly enables a carpet roll on the very next turn** (i.e., you're one prime away from making a chain ≥ 3 and have turns left to carpet it).
4. **Plain step only to reach a carpet-able chain**.
5. **Consider rat guesses more aggressively** as the endgame threshold kicks in (see rat policy doc §4).

**Turn Budget Awareness**:
With `k` turns remaining:
- If a chain of length `n` needs `m` more primes before it can be carpeted: only invest if `m + 1 ≤ k` (need turns to prime AND carpet).
- If `k ≤ 2` and no chain ≥ 3 is adjacent: prime if possible (guaranteed +1/turn), otherwise plain step is a total waste — consider rat search.

**Last-Turn Rule**: On the final turn, the only options that generate points are:
- Carpet an adjacent chain (if one exists).
- Successful rat catch (+4).
- Prime step (+1 as consolation).
Never plain step on the last turn.

---

## 2) Prime Placement Strategy

Prime placement is the single most consequential non-search decision. A well-placed prime contributes to a future 15–28 point carpet sequence. A poorly-placed prime earns exactly 1 point total.

**Realistic chain length targets**: Geometric analysis of the 8×8 board with all 81 possible corner-block configurations confirms that length-7 chains are always *geometrically* possible — even the worst-case config (e.g. TL=2×3, TR=3×2, BL=3×2, BR=2×3) still has 4 rows/columns with 7+ unblocked cells. However, these L7-capable lines all pass through the center where both players spawn and compete. In practice, the opponent's primes and position will interrupt most L7 attempts. **Target L5 as the structural goal (2.5 pts/turn). Treat L6–L7 as opportunistic windfalls, not planned sequences.**

### 2.1 Prime Direction Selection

When multiple prime directions are available, score each by:

```
PrimeScore(dir) =
    w_chain * contiguous_primeable_ahead(dir)
  + w_align * alignment_with_existing_chain(dir)
  + w_center * centrality_of_destination(dir)
  - w_opp * proximity_to_opponent_primes(dir)
  - w_trap * trap_risk(dir)
```

**Recommended weights (initial)**:
| Weight | Value | Rationale |
|--------|-------|-----------|
| `w_chain` | 3.0 | Long chain potential is dominant |
| `w_align` | 2.5 | Extending an existing chain >>> starting a new one |
| `w_center` | 0.5 | Central primes have more extension options |
| `w_opp` | 0.3 | Mild penalty for building near opponent's territory |
| `w_trap` | 4.0 | Highest penalty — never walk into a dead end |

### 2.2 "Contiguous Primeable Ahead" Calculation

For a direction `d` from position `(x, y)`:
```
count = 0
pos = destination(x, y, d)
while pos is valid_cell AND pos is SPACE (not blocked, primed, carpet, or occupied):
    count += 1
    pos = next_in_direction(pos, d)
return count
```

### 2.3 "Alignment with Existing Chain" Calculation

Check whether the destination square, when primed, would extend the *same* linear chain in the *reverse* direction:
```
For the reverse of direction d:
  count how many contiguous PRIMED cells exist behind the current position.
  alignment = that count
```
If `alignment >= 1`, this prime extends an existing chain (very valuable). If `alignment >= 3`, this prime brings a chain to carpetable length (extremely valuable).

### 2.4 Prime Anti-Patterns (Hard Rules)

These should be implemented as **hard vetoes**, not soft penalties:

1. **Never prime into a dead end**: If the destination has ≤ 1 non-primed, non-blocked exit and that exit leads to another constrained position, **veto**.
2. **Never prime if it would make a chain uncarpetable**: If priming in direction `d` blocks the only approach path needed to initiate a carpet roll on the chain, **veto**.
3. **Never prime adjacent to the opponent's position if it restricts YOUR future carpet approach**: Priming a square that the opponent can stand on to block your carpet entry is actively harmful.

---

## 3) Carpet Execution Strategy

Carpet rolls are the primary scoring mechanism. Optimal carpet timing is the difference between a 15-point game and a 40-point game.

### 3.1 Carpet Opportunity Evaluation

On every turn, scan all four cardinal directions from the current position for adjacent contiguous primed chains. Score each:

```
CarpetValue(dir, length) =
    carpet_table[length]
  - opportunity_cost_of_not_extending
  + urgency_bonus
```

Where:
- `carpet_table` = `{1:-1, 2:2, 3:4, 4:6, 5:10, 6:15, 7:21}`
- `opportunity_cost_of_not_extending`: If one more prime turn would increase the length by 1 and the next tier's points minus this tier's points exceeds 2, then `opportunity_cost = tier_delta - 1` (the -1 accounts for the prime point you'd earn while extending).
- `urgency_bonus`: Increases as turns remaining decreases. When `turns_left <= chain_length + 2`, add +3 urgency to prevent stranding.

### 3.2 Carpet Timing Decision Table

| Chain Length | Next-Tier Gain (pts) | Extend? | Condition to Carpet NOW |
|-------------|---------------------|---------|------------------------|
| 1 | — | N/A | **NEVER** carpet length 1 (−1 pts) |
| 2 | +2 (→3: 4pts) | YES | Only if turns_left ≤ 2 |
| 3 | +2 (→4: 6pts) | YES if safe | If blocked from extending, or turns_left ≤ 4 |
| 4 | +4 (→5: 10pts) | **ALWAYS** extend | Unless turns_left ≤ 2, always add one more prime |
| 5 | +5 (→6: 15pts) | Consider extending | Unless turns_left ≤ 3, opponent threatens, or L7 line is contested |
| 6 | +6 (→7: 21pts) | Context-dependent | Only extend if the extension cell is uncontested AND turns_left ≥ 3 |
| 7 | — (max) | Carpet NOW | Always carpet at length 7 immediately |

**Note on L6→L7 extension**: While L7 is geometrically possible in every corner configuration, all L7-capable lines pass through the center zone where both players operate. Attempting to hold 7 contiguous uninterrupted primed cells through this area is fragile. Prefer carpeting at L5-L6 rather than risking the opponent priming/stepping into your chain.

### 3.3 Carpet Approach Planning

When not adjacent to a carpetable chain, plan a path to the carpet entry point:

1. **Identify the optimal entry end** of each chain. Carpet should be rolled from one end to the other. The entry square is the empty square adjacent to one endpoint of the chain.
2. **Choose the entry point that gives a better post-carpet position**: After rolling, you end up at the opposite end of the chain. Prefer the entry that leaves you in a position with high mobility and near other priming opportunities.
3. **Reposition cost must use actual walkable distance, NOT Manhattan distance**. As the game progresses, primed squares become walls for plain steps (you cannot plain-step onto primed squares). A destination that is Manhattan-distance 2 away may be actually unreachable or require 5+ steps to navigate around primed walls. The agent must compute reachable-path distance through non-blocked, non-primed, non-occupied cells. Maximum acceptable actual-path reposition cost: 2 steps. If actual path is longer, consider alternative scoring paths.

### 3.4 Carpet Fragmentation Penalty (Board Scarring)

**Critical rule**: Carpeted squares are **permanent dead zones** for future chain building. You cannot prime on a carpeted square (`board.py` §5.3: "Current square must be SPACE"). When you carpet a chain, every square in that chain becomes permanently unavailable for future prime infrastructure.

This creates a board fragmentation problem:
- A carpet through the center of the board **severs** prime corridors, potentially isolating half the board from future chain-building.
- Early/mid-game carpets in the center 4×4 are especially destructive — they cut through the highest-connectivity region.
- A carpet along row 3 or 4 can make it impossible to build north-south chains through those cells for the rest of the game.

**Scoring integration**: Add `S_fragmentation` as a penalty for carpets that bisect usable board space:
```
S_fragmentation(carpet_action) =
    fragmentation_weight * (accessible_regions_after - accessible_regions_before)
```
Where `accessible_regions` counts the number of connected components of SPACE cells reachable by the player after carpeting. If carpeting increases connected components (fragments the board), apply a penalty.

**Heuristic shortcut**: For carpet actions through the center rows/cols (2–5), add a flat penalty of `−0.4 * carpet_length` to the score if the carpet eliminates all SPACE cells in a cross-section of the board.

### 3.5 Carpet Landing Awareness

After a carpet roll of length `k`, you land on the `k`-th square. This is now a **carpeted** square. Plan the next move:
- You can plain-step or prime-step from the landing position (carpeted squares are walkable).
- If the landing position has good prime extension in a new direction, immediately begin a new chain.
- If the landing is in a corner or low-mobility area, this reduces the carpet's net value (you waste turns escaping).
- **The landing square is carpeted, not space** — you cannot prime FROM the landing square on your next turn (prime requires current square to be SPACE). You must first plain-step off the carpet to a SPACE cell before you can resume priming.

**Rule**: Prefer carpet directions where the landing square has ≥ 3 open exits AND at least one exit leads to a SPACE cell (not carpet, not primed, not blocked) to enable immediate prime resumption.

---

## 4) Spatial Control & Mobility

### 4.1 Mobility as a Resource

Mobility = number of legal moves from current position. Low mobility means:
- Fewer scoring options per turn.
- Higher risk of being trapped by the opponent.
- Fewer escape routes if board state changes (opponent primes around you).

**Target**: Maintain ≥ 3 legal non-search moves at all times. If a move would drop you below this threshold, apply a severe penalty (via `S_risk` in scoring).

### 4.2 Centrality Bias

Central squares (closer to `(3.5, 3.5)`) have higher average connectivity and more directions for chain building. The centrality component in scoring provides a mild pull toward the center, preventing the agent from drifting into corners where it becomes ineffective.

```
centrality(x, y) = 1.0 - manhattan_distance((x, y), (3.5, 3.5)) / 7.0
```

**Phase modulation**:
- Opening: Centrality weight ×1.5 (important to claim central corridors)
- Mid-game: Centrality weight ×1.0 (balance with chain completion)
- Late game: Centrality weight ×0.3 (irrelevant; only points matter)

### 4.3 Board Region Classification

Divide the 8×8 board into regions for strategic reasoning:

| Region | Squares | Properties |
|--------|---------|------------|
| Center 4×4 | (2,2)–(5,5) | Highest connectivity, spawn zone |
| Extended center | (1,1)–(6,6) minus center | Good connectivity, chain extension zone |
| Edges | Row 0, Row 7, Col 0, Col 7 minus corners | One-directional limit |
| Corners | (0,0)–(2,2), (5,0)–(7,2), etc. | Likely blocked, dangerous |

**Corner awareness**: Each corner has a randomly placed blocked rectangle (2×2, 2×3, or 3×2). At game start, immediately identify blocked squares and blacklist the 3–6 blocked cells per corner from prime planning.

---

## 5) Opponent Denial & Interaction

### 5.1 When to Deny

Denial (restricting opponent mobility or carpet access) has a cost: you spend a turn not scoring for yourself. Denial is only worthwhile when:

1. **The denial prevents a high-value opponent carpet** (length ≥ 5). Standing on or priming the carpet entry/exit square to block a 10+ point carpet is a legitimate tempo investment.
2. **The denial is "free"** — you're priming in a direction that happens to also block the opponent's chain extension.
3. **You are ahead on points and want to run out the clock**. In this case, reducing both players' scoring rates favors the leader.

### 5.2 When NOT to Deny

- ❌ Don't chase the opponent across the board to block a length-3 carpet (costs you turns; net gain is small).
- ❌ Don't sacrifice your own chain-building to trap the opponent (unless the trap is guaranteed and devastating).
- ❌ Don't use primes defensively if you could use them offensively for a chain ≥ 4.

### 5.3 Denial Scoring Integration

The `S_denial` component in the scoring formula:
```
S_denial = max(0, 8 - opponent_legal_moves) / 8
```

This is a **passive** assessment: it rewards moves that happen to reduce opponent mobility. The `d` coefficient (default 0.35, adaptive range [0.20, 0.55]) controls how much weight this gets.

**Phase modulation**:
- Opening: `d` weight ×0.5 (focus on own infrastructure)
- Mid-game: `d` weight ×1.0 (balanced)
- Late game: `d` weight ×1.5 (if ahead, lock opponent out; if behind, irrelevant — score instead)

### 5.4 Opponent Carpet Blocking

If the opponent has a chain of length ≥ 5 and you can occupy or prime the entry square:
- **If it costs 0–1 turns to reach**: Block. Denying 10+ opponent points for 1 turn is excellent ROI.
- **If it costs 2+ turns**: Only block if your own prime yield during those turns is ≤ 2 points. Otherwise, build your own scoring infrastructure.

---

## 6) Self-Trap Avoidance

Self-trapping (entering a position with ≤ 1 exit) is one of the most catastrophic mistakes possible. It wastes turns escaping and potentially strands prime chains uncarpeted.

### 6.1 Trap Detection

Before executing any move, compute post-move exit count:
```
exits = number of non-blocked, non-primed, non-occupied neighbors of destination
```

**Hard rule**: If `exits == 0`, the move is **illegal** (trapped). Never select.
**Soft rule**: If `exits == 1`:
- Apply `+0.3` to `S_risk` (critical penalty in scoring).
- Verify the single exit doesn't lead to another 1-exit position (cascade trap).
- Only accept if this is the SOLE remaining legal non-search move.

### 6.2 Corridor Trap Recognition

A "corridor trap" is: destination has exactly 1 exit, and that exit leads to a square that also has ≤ 2 exits. This often happens when priming along an edge or near blocked corners.

**Detection**:
```
if post_move_exits <= 1:
    single_exit_dest = the single available exit square
    exits_of_exit = count valid exits from single_exit_dest (excluding current)
    if exits_of_exit <= 1:
        CORRIDOR_TRAP = True → veto this move unless no alternative
```

### 6.3 Primed-Wall Awareness

Your own primes create walls! A prime step primes the square you DEPART from. This means:
- If you prime and then want to go back, you can't (can't plain-step onto primed squares).
- Priming in a narrow corridor can seal the corridor behind you.
- As mid-game progresses, primed walls from BOTH players progressively restrict plain-step mobility. Board regions that appear adjacent by Manhattan distance may become unreachable without carpet-rolling through primed walls.

**Rule**: Before priming, verify that the destination square has at least 2 exits not counting the square you're about to prime (the one you're departing).

### 6.4 Mid-Game Mobility Collapse

As both players prime the board, plain-step connectivity degrades rapidly. By turn 20–25, large sections of the board may be inaccessible via plain steps. This has critical implications:

1. **Reposition cost escalates non-linearly**: What was a 2-step reposition at turn 10 may be 5+ steps or impossible at turn 25.
2. **Carpet approach planning must use actual walkable-path distance**, not Manhattan distance. Compute BFS/flood-fill through cells that are not blocked, not primed, and not occupied.
3. **Priming along edges creates one-way corridors**: If you prime along row 0 heading right, you cannot return left through those primed cells. Plan your priming direction so you're moving TOWARD your next carpet opportunity, not away from it.
4. **Carpet rolls become the only way to traverse primed regions**: This is an important secondary value of carpeting — it converts walls into walkable terrain. Factor this connectivity benefit into carpet timing decisions.

---

## 7) Refined Scoring Formula

The total scoring formula for non-search candidates:

```
S_total = a * S_immediate
        + b * S_position
        + c * S_carpet_setup
        + d * S_denial
        - f * S_risk
        - g * S_fragmentation
```

Where `g = 0.50` (fragmentation penalty weight). `S_fragmentation = 0` for all non-carpet actions.

### 7.1 Component Definitions (Enhanced)

| Component | Formula | Range | Notes |
|-----------|---------|-------|-------|
| `S_immediate` | Prime=1, Carpet(k)=table[k], Plain=0 | [−1, 21] | Raw point gain this turn |
| `S_position` | `post_move_count/4 + 0.3*centrality` | [0, ~2.3] | Mobility + board position |
| `S_carpet_setup` | Max carpet_table value over all cardinal directions with ≥ 2 contiguous primed cells from destination | [0, 21] | Future carpet potential. If action is prime, include newly primed cell in projection |
| `S_denial` | `max(0, 8 - opp_moves) / 8` | [0, 1] | Opponent mobility restriction |
| `S_risk` | `max(0, 1 - post_moves/4) + 0.3*I(single_exit_chokepoint)` | [0, 1.3] | Danger of getting trapped |
| `S_fragmentation` | Carpet actions only: penalty for severing board connectivity (see §3.4) | [0, ~2.8] | Prevents permanently fragmenting the grid |

### 7.2 Phase-Dependent Coefficient Modulation

Beyond the adaptive opponent-model adjustments (see `adaptation.py`), apply phase-based scaling to shift strategy priorities:

| Coefficient | Base | Opening (t<12) | Mid (12–30) | Late (>30) | Rationale |
|-------------|------|----------------|-------------|------------|-----------|
| `a` (immediate) | 1.00 | ×0.9 | ×1.0 | ×1.3 | Late game: cash out NOW |
| `b` (position) | 0.45 | ×1.3 | ×1.0 | ×0.5 | Early: position matters; late: irrelevant |
| `c` (carpet setup) | 0.60 | ×1.2 | ×1.3 | ×0.4 | Mid: chain completion peak; late: no time to build |
| `d` (denial) | 0.35 | ×0.5 | ×1.0 | ×1.5 | Late: denial matters if ahead |
| `f` (risk) | 0.75 | ×1.2 | ×1.0 | ×0.6 | Early: protect mobility; late: take risks for points |

**Implementation**: Multiply base × phase modifier BEFORE applying adaptive opponent-model deltas. The adaptive deltas from `adaptation.py` further adjust `a`, `c`, `d`, `f` within their clamp envelopes.

### 7.3 Tie-Breaking Rules

When two non-search actions have the same `S_total`:
1. Higher post-move mobility wins.
2. Higher immediate point gain wins.
3. Lower risk wins.
4. Carpet continuation (same direction as last move if extending a chain) wins.
5. Deterministic move-sort-key order (by type, direction, length).

---

## 8) Special Situations

### 8.1 "No Good Move" Scenarios

Sometimes all available moves are bad (low exits everywhere, no chains ready). In this case:
1. If a rat search has even marginally positive EV (p1 > 1/3 ≈ 0.333), search.
2. Otherwise, prime in the direction with the most future primable squares (even if the chain is short).
3. If only plain steps are available, move toward the nearest primable corridor.
4. As absolute last resort, take any legal move (deterministic by sort key).

### 8.2 Opponent Collision Avoidance

Two workers cannot occupy the same square. If the highest-scored destination is occupied by the opponent:
- The move is **invalid** and should be filtered during candidate generation (the engine handles this).
- But strategically: if the opponent is blocking your carpet entry, consider priming around them or waiting 1 turn (they'll likely move).

### 8.3 Score-Deficit Acceleration

When behind by `Δ` points with `k` turns remaining, compute minimum required scoring rate:
```
required_rate = Δ / k
```

| Required Rate | Strategy Shift |
|---------------|---------------|
| < 1.0 | Normal play; steady priming will catch up |
| 1.0 – 2.0 | Prioritize existing carpets; consider shorter carpet rolls |
| 2.0 – 3.5 | Rush to any available carpet ≥ 4; accept risk |
| > 3.5 | Must catch rat or carpet length ≥ 6; otherwise likely losing |

This shifts the `a` coefficient upward (favor immediate points) and the `c` coefficient downward (stop building for the future).

### 8.4 Score-Lead Conservation

When ahead by `Δ` points with `k` turns remaining:
- If `Δ > 3 * k`: Victory is nearly guaranteed. Play safe, avoid traps, do simple primes.
- If `Δ > k`: Lead is comfortable. Prioritize denial and safe scoring.
- If `Δ ≤ k`: Lead is fragile. Play to maximize own score; don't waste turns on denial.

---

## 9) Integration with Rat Policy

The movement strategy and rat guess policy share one decision point per turn: **should I move or should I search?**

The integration contract (from `final_rat_tracking_and_guess_policy.md`):

1. **Standard mode (r_me > 3)**: Compute `Q_best_non` from the best non-search action's immediate point gain. Search iff `6*p1 - 2 >= Q_best_non + 0.5`.
2. **Endgame mode (r_me ≤ 3)**: Win-probability maximization directly compares search and non-search actions. The movement strategy provides `M_non(board, k)` to the endgame evaluator.

**What this document controls**: Everything that determines `Q_best_non` and which non-search action is best. The scoring formula, prime placement, carpet timing, mobility management — all of these determine the quality of the non-search option that competes with the rat guess.

**Key principle**: A strong movement strategy raises `Q_best_non`, which raises the bar for rat guesses. This is GOOD — it means the agent only guesses when belief is truly concentrated, avoiding costly −2 misses. The goal is not to suppress rat guesses, but to ensure that when a guess is declined, the alternative action is genuinely valuable.

---

## 10) Decision Flowchart (Per-Turn, Non-Search)

```
START: Is emergency mode? → YES → Return first safe valid move
                           ↓ NO
Is a carpet length ≥ 5 adjacent? → YES → Carpet it (unless extending by 1 earns +4 and turns allow)
                                    ↓ NO
Is a carpet length 3–4 adjacent? → YES → Is extension possible & profitable with turns left?
                                    |       → YES → Prime to extend
                                    |       → NO  → Carpet it
                                    ↓ NO
Am I adjacent to a chain I should extend? → YES → Prime in chain direction
                                             ↓ NO
Can I start a new chain in a high-value corridor? → YES → Prime in best direction
                                                    ↓ NO
Can I reposition to a chain entry in ≤ 2 actual walkable steps? → YES → Plain step toward it
  (using BFS through non-blocked, non-primed, non-occupied cells)
                                                                  ↓ NO
Prime in the direction with most future potential → (fallback)
```

This flowchart produces the **non-search candidate** that competes with the best rat search candidate via the guess gate.

---

## 11) Implementation Mapping

| Strategy Concept | Implementation Location | Current Status |
|-----------------|------------------------|----------------|
| Phase detection | `TimeManager.phase_multiplier()` | ✅ Implemented (turn_count thresholds) |
| Scoring formula | `PolicyEngine.score_non_search()` | ✅ Implemented |
| Carpet chain scan | `PolicyEngine._chain_score()` | ✅ Implemented (basic) |
| Trap risk | `PolicyEngine._risk_score()` | ✅ Implemented (basic) |
| Opponent denial | `PolicyEngine.score_non_search()` via `S_denial` | ✅ Implemented |
| Adaptive coefficients | `adaptation.py` | ✅ Implemented |
| Carpet fragmentation penalty (§3.4) | `PolicyEngine.score_non_search()` | ✅ Implemented |
| T-matrix farmability check (§12) | `PolicyEngine.__init__` / `RuntimeState` | ✅ Implemented (proactive flag) |
| Phase-dependent coefficient modulation (§7.2) | `PolicyEngine._get_phase()` / `_phase_multipliers()` in `select_action` | ✅ **Implemented** |
| Prime direction optimization (§2.1) | `PolicyEngine._prime_direction_bonus()` / `_contiguous_primeable_ahead()` / `_chain_alignment_behind()` | ✅ **Implemented** |
| Carpet timing logic (§3.2) | `PolicyEngine._carpet_timing_adjustment()` / `_can_extend_chain()` | ✅ **Implemented** |
| Corridor trap detection (§6.2) | `PolicyEngine._corridor_trap_penalty()` | ✅ **Implemented** |
| Score-deficit acceleration (§8.3) | `PolicyEngine._apply_score_pressure()` | ✅ **Implemented** |
| Score-lead conservation (§8.4) | `PolicyEngine._apply_score_pressure()` | ✅ **Implemented** |
| Hard constraints (§13) | `score_non_search()` vetoes + `select_action()` last-turn filter | ✅ **Implemented** |

### 11.1 Priority Implementation Order

1. **Phase-dependent coefficient modulation** (§7.2) — ✅ Done. Phase multipliers applied in `select_action` after adaptation, restored before return.
2. **Carpet fragmentation penalty** (§3.4) — ✅ Done. `_count_space_components` flood-fill in `_fragmentation_score`.
3. **Prime direction optimization** (§2.1–2.3) — ✅ Done. `_prime_direction_bonus` with `_contiguous_primeable_ahead` + `_chain_alignment_behind`.
4. **Carpet timing logic** (§3.2) — ✅ Done. `_carpet_timing_adjustment` with `_can_extend_chain`; hard L1 veto, L2/L3/L4 discouragement, L5+/L7 bonuses.
5. **Corridor trap detection** (§6.2) — ✅ Done. `_corridor_trap_penalty` looks one step beyond a single-exit position.
6. **Walkable-path reposition distance** (§3.3, §6.4) — Partially addressed via mobility scoring; full BFS-based reposition planner deferred (low marginal value given scoring approach).
7. **Score-deficit acceleration** (§8.3) + **Score-lead conservation** (§8.4) — ✅ Done. `_apply_score_pressure` modulates effective coefficients.
8. **Hard constraints** (§13) — ✅ Done. 0-exit veto, carpet-L1 veto, last-turn plain-step filter.

---

## 12) T-Matrix Farmability Analysis

The user's concern about "rat farming" (repeatedly catching a rat stuck in an absorbing state or tight loop) was investigated against all four transition matrices in this repo:

| Matrix | max(b_reset) | Top-5 mass | Entropy (bits) | Farmable? |
|--------|-------------|------------|----------------|----------|
| bigloop.pkl | 0.030 | 0.138 | 5.85 | No |
| hloops.pkl | 0.035 | 0.167 | 5.72 | No |
| quadloops.pkl | 0.025 | 0.125 | 5.89 | No |
| twoloops.pkl | 0.035 | 0.171 | 5.70 | No |

No matrix has absorbing states (max self-loop < 0.8) or strong 2-cycles (no pair with both T[i,j] > 0.4 and T[j,i] > 0.4). The stationary distributions are nearly uniform (entropy near 6 = log2(64) bits). After 1000 steps from (0,0), the rat spreads across the board.

With ±10% perturbation applied at runtime, these properties won't change meaningfully. **Rat farming is not viable in this repo's matrix set.** The agent should not deprioritize board movement in favor of repeated searches on a "hotspot."

**Proactive check (implemented in constructor)**: Compute `max(b_reset)` at game start. If `max(b_reset) > 0.25` (indicating a highly concentrated stationary distribution — possible with custom tournament matrices), set a `farmable_rat` flag that shifts the search threshold down and reduces movement priority. This check costs negligible time since `b_reset` is already computed.

---

## 13) Non-Negotiable Movement Constraints

1. **Never carpet length 1** (−1 point; strictly dominated by any other action).
2. **Never enter a 0-exit position**.
3. **Never plain step on the last turn** if any point-generating action exists.
4. **Never prime into a position that makes your own best chain uncarpetable**.
5. **Always validate moves** with `board.is_valid_move()` before selection.
6. **Always maintain emergency timing guard** — return a valid move before timeout.
7. **Scoring formula must use effective (post-adaptation) coefficients**, not raw base coefficients.
8. **Carpet scoring uses the official table** — never approximate or interpolate.
9. **Candidate generation must include all legal non-search moves** — never artificially prune before scoring.
10. **Deterministic tie-breaking** — same state + same seed → same action, always.
11. **Reposition distance must be actual walkable-path distance** through non-blocked, non-primed cells — never Manhattan distance.
12. **Carpet actions must account for board fragmentation** — never carpet through the center without evaluating connectivity impact.
