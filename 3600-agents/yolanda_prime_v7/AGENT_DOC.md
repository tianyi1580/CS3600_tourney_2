# Yolanda Prime v7 (Best-in-Class Hybrid)

The definitive version of the Yolanda Prime bot, synthesizing the strengths of 
v5.1 (disciplined search & tactical aggression) with v6 (adaptive resiliency).

## Synthesis Strategy

1. **v5.1 Proven Search Logic** — Retains the hard p_max gate (0.45), nearly 
   zeroed denial equity (0.02x lambda), and conservative panic-mode margin 
   adjustment (-0.05).
2. **v6 Adaptive Resiliency** — Keeps the **Opening Territory Boost** (fixes 
   early-game collapses) and the **Late-game Deficit Gate** (prevents search 
   suicides when behind).
3. **v7 Refinements**:
   - **Moderate Deficit Adaptation**: The v6 scoring/chain boosters were tuned 
     down to 1.2x (from 1.4x/1.5x) to prevent "greed-trap" regressions while 
     maintaining an aggressive comeback profile.
   - **Search Hysteresis**: Penalizes consecutive search misses by increasing 
     the search margin, preventing "drilling empty holes" when belief is stale.
   - **Tuned Time Budget**: Reverted `time_reserve` to 2.5 (from v6's 5.0) to 
     maximize mid-game tactical depth while ensuring survival.

## Pipeline Components (v7)

1. **Belief** — HMM tracking with search feedback integration.
2. **Bitboard architecture** — PVS search with TT, LMR, and NMP.
3. **Territory-Aware Leaf Eval** — Five-term evaluator with dynamic overrides.
4. **Adaptive Orchestrator**:
   - **George Filter**: Slashes denial for greedy bots.
   - **Opening Phase**: 1.5x Territory bias.
   - **Deficit Mode**: 1.2x Point/Chain bias.
5. **Search vs Move Policy** — Hybrid policy with denial-equity suppression 
   and hysteresis.

## Historical Performance Reference

- **v5.1 vs v6**: v5.1 dominated (Elo +85) by having better search discipline 
  and a more aggressive time budget.
- **v7 Goal**: Achieve a strict win-rate advantage over v5.1 by adding the 
  adaptive resiliency of v6 without the over-suppression of searches.
