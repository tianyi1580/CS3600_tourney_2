# Yolanda Prime v4.7

Elite-tier evolution building on the v3 bitboard architecture. v4.7 introduces 
the **George Filter** for sub-optimal bot detection, aggressive time preservation, 
forecast-based leaf evaluation, and search optimizations like Null-Move Pruning.

## Pipeline

1. **Belief** — HMM tracking (`tracking/belief.py`).
2. **Bitboard state** — `infra/bitboard.py` with precomputed masks and Zobrist keys.
3. **Territory** — `strategy/territory.py` Voronoi with carpet-potential lookup.
4. **Planner** — `strategy/carpet_planner.py` straight-ray/elbow-chain DP.
5. **Search (v4 Optimized)** — `strategy/search/alphabeta.py` PVS with TT, LMR, 
   and **Null-Move Pruning (NMP)** for +1-2 depth plies.
6. **Leaf eval (v4 Forecast)** — `strategy/leaf_eval.py` multi-term evaluator with 
   **Forecast-Based Rat Hotspots**. Proximity to future rat locations is rewarded.
7. **Adversarial Adaptation (v4.7)** — `strategy/orchestrator.py` detects opponent 
   move patterns and dynamically adjusts leaf eval coefficients.
8. **Information foraging** — Gated positional info gain.
9. **Search policy** — Denial-equity decision rule.
10. **Time manager (v4.7 Optimized)** — Ultra-conservative budget allocation.

## v4.7 Key Enhancements

### The George Filter (Sub-optimal Bot Detection)
v4.7 includes a heuristic to detect opponents that lack lookahead (characterized by 
an excess of PLAIN/greedy steps).
- **Trigger:** Opponent `PLAIN` step ratio > 35% after turn 15.
- **Action:** Slashes `lambda_denial` to 0.05 and boosts `alpha` (point scoring) 
  by 30%. This prevents wasting resources on "denying" searches the opponent 
  isn't performing, allowing the agent to focus entirely on score accumulation.

### Conservative Time Management
v4.7 implements a much tighter time reserve strategy to ensure survival in 
prolonged matches:
- **Fraction Cap:** Reduced from 0.40 to **0.15**, limiting the maximum time 
  spent on any single turn.
- **Phase Multipliers:** Aggressive reductions in opening (2.5 -> 1.2) and late-game 
  (1.8 -> 0.8) multipliers to build a significant time buffer.

### Null-Move Pruning (NMP)
In branches where the stand-pat evaluation is already above Beta, we perform a 
reduced-depth search after "passing" the turn. This allows the agent to reach 
depths of 6-7 in the time budget previously required for depth 5.

### Forecast-Based Hotspots
Instead of only evaluating where the rat is *now*, v4 uses the transition 
matrix to project the rat's probability distribution 3 turns (6 single-steps) 
into the future. Proximity to these "forecasted hotspots" biases worker movement 
toward interception points.

### Adversarial Overrides
The `RuntimeState` buffer of opponent categories is analyzed at each turn start:
- **Carpet-heavy opponents:** Evaluation shifts to increase `omega_threat` and 
  territory defensiveness.
- **Search-heavy opponents:** Evaluation shifts to increase `alpha`, focusing 
  more on raw score accumulation to outpace their info gain.

## Verification

### Local Scrimmage
```bash
python scrimmage.py yolanda_prime_v4_7 yolanda_prime_v3 5
```

### Component Tests
```bash
# Test NMP logic
python -m unittest CS3600_tourney/tests/test_search_v4.py

# Test Adaptation & Filter
python -m unittest CS3600_tourney/tests/test_adaptation.py
```
