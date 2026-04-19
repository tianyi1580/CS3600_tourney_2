# Yolanda Prime v3

Ground-up rewrite that replaces v2's heuristic hot path with a bitboard
iterative-deepening alpha-beta search, a Voronoi-based territory evaluator,
and a multi-turn chained-carpet planner.

## Pipeline

1. **Belief** — ported HMM from v2 (`tracking/belief.py`).
2. **Bitboard state** — `infra/bitboard.py` with precomputed adjacency/ray masks
   and Zobrist keys seeded from the transition matrix.
3. **Territory** — `strategy/territory.py` dual-BFS Voronoi with carpet-potential
   ray lookup.
4. **Planner** — `strategy/carpet_planner.py` straight-ray and elbow-chain DP over
   the Voronoi-safe subregion.
5. **Search** — `strategy/search/alphabeta.py` iterative-deepening PVS with TT,
   LMR, killer/history ordering, carpet-only quiescence.
6. **Leaf eval** — `strategy/leaf_eval.py` five-term evaluator.
7. **Information foraging** — `strategy/info_foraging.py` gated on high
   normalized belief entropy.
8. **Search policy** — `strategy/search_policy.py` denial-equity fire-search
   decision rule.
9. **Time manager** — `infra/time_manager.py` soft/hard deadline with
   complexity multiplier.

Entrypoint: `yolanda_prime_v3.agent.PlayerAgent`.

## Hyperopt (stages 1–4)

All four stages use `scripts/optimize_yp3_weights.py` (CMA-ES via pycma) and
the ladder defined in `workflows/yp3_hyperopt.py`. Candidate weights are
injected through `YP3_WEIGHTS_JSON`; opponents in the ladder are untouched.

Local preflight (quick sanity check, seconds):

```bash
PYTHONPATH=engine:3600-agents:. python -c \
  "from scripts.optimize_yp3_weights import _verify_weight_channel_isolation; \
   _verify_weight_channel_isolation(); print('OK')"
```

Stage 1 — tier-A leaf-eval coefficients (`alpha`, `beta`, `gamma`, `delta`,
`epsilon`, `omega_threat`, plus tier-B planner/territory/chain scales):

```bash
python scripts/optimize_yp3_weights.py \
  --profile core --ladder hyperopt --evaluation-profile tuning \
  --algo cma --generations 30 --population 24 --sigma 0.25 \
  --workers 16 --seed 42 \
  --output-dir data/hyperopt/yolanda_prime_v3/stage1
```

Stage 2 — widen to time-manager multipliers (tier-D knobs, via `extended`
profile but the optimizer will still mostly refine tier-A/B around the
Stage 1 optimum because CMA's covariance is seeded from the best vector):

```bash
python scripts/optimize_yp3_weights.py \
  --profile extended --ladder hyperopt --evaluation-profile tuning \
  --algo cma --generations 25 --population 24 --sigma 0.18 \
  --workers 16 --seed 102 --resume \
  --initial-weights-file data/hyperopt/yolanda_prime_v3/stage1/best_weights.json \
  --output-dir data/hyperopt/yolanda_prime_v3/stage2
```

Stage 3 — search-policy lambdas (`phase` profile focuses tier-C):

```bash
python scripts/optimize_yp3_weights.py \
  --profile phase --ladder hyperopt --evaluation-profile tuning \
  --algo cma --generations 20 --population 20 --sigma 0.15 \
  --workers 16 --seed 202 \
  --initial-weights-file data/hyperopt/yolanda_prime_v3/stage2/best_weights.json \
  --output-dir data/hyperopt/yolanda_prime_v3/stage3
```

Stage 4 — joint A-tier fine-tuning at narrow sigma:

```bash
python scripts/optimize_yp3_weights.py \
  --profile core --ladder hyperopt --evaluation-profile tuning \
  --algo cma --generations 20 --population 16 --sigma 0.08 \
  --workers 16 --seed 302 \
  --initial-weights-file data/hyperopt/yolanda_prime_v3/stage3/best_weights.json \
  --output-dir data/hyperopt/yolanda_prime_v3/stage4
```

After each stage, run the master batch suite for regression evidence:

```bash
python scripts/run_master_batch_suite.py \
  --candidate yolanda_prime_v3 \
  --candidate-weights-file \
    data/hyperopt/yolanda_prime_v3/stage<N>/best_weights.json
```

> Stage 1 evaluates ~330 games/candidate × 24 candidates × 30 generations ≈
> 240k games at ~25 s/game ≈ 1,600 CPU-hours. All four stages must run on
> PACE (or equivalent cluster); local execution is not feasible.
