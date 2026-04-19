# Yolanda Prime v4

Elite-tier evolution building on the v3 bitboard architecture. v4 introduces 
adversarial style adaptation, forecast-based leaf evaluation, and search 
optimizations for deeper plies.

## Pipeline

1. **Belief** — HMM tracking (`tracking/belief.py`).
2. **Bitboard state** — `infra/bitboard.py` with precomputed masks and Zobrist keys.
3. **Territory** — `strategy/territory.py` Voronoi with carpet-potential lookup.
4. **Planner** — `strategy/carpet_planner.py` straight-ray/elbow-chain DP.
5. **Search (v4 Optimized)** — `strategy/search/alphabeta.py` PVS with TT, LMR, 
   and **Null-Move Pruning (NMP)** for +1-2 depth plies.
6. **Leaf eval (v4 Forecast)** — `strategy/leaf_eval.py` multi-term evaluator with 
   **Forecast-Based Rat Hotspots**. Proximity to future rat locations is rewarded.
7. **Adversarial Adaptation (v4)** — `strategy/orchestrator.py` detects opponent 
   move patterns (e.g., Carpet-heavy vs Search-heavy) and dynamically adjusts 
   leaf eval coefficients (`omega_threat`, `alpha`, etc.).
8. **Information foraging** — Gated positional info gain.
9. **Search policy** — Denial-equity decision rule.
10. **Time manager** — Dynamic budget allocation with complexity scaling.

## v4 Key Enhancements

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
The `RuntimeState` buffer of opponent categories is analyzed at each turn start.
- **Carpet-heavy opponents:** Evaluation shifts to increase `omega_threat` and 
  territory defensiveness.
- **Search-heavy opponents:** Evaluation shifts to increase `alpha`, focusing 
  more on raw score accumulation to outpace their info gain.

## Verification

### Local Scrimmage
```bash
python scrimmage.py yolanda_prime_v4 yolanda_prime_v3 5
```

### Component Tests
```bash
# Test NMP logic
python -m unittest CS3600_tourney/tests/test_search_v4.py

# Test Adaptation
python -m unittest CS3600_tourney/tests/test_adaptation.py
```
