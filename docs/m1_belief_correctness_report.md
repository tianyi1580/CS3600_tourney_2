# M1 Belief Correctness Report

Evidence for milestone M1 (*Belief and Search Core*) per `bot_plan_v4.md`: normalization and respawn reset parity, plus search-precision comparison vs a random-search baseline. Ground rules: `assignment_spec.md` for belief semantics (`§10.4`) and search EV (`§10.6`).

## 1. Normalization and non-negativity

| Invariant | Enforcement |
| --- | --- |
| Posterior sums to `1.0` after `predict()` / `update()` | `tests/test_belief_engine.py::test_predict_update_is_normalized` |
| Long chains stay normalized | `tests/test_belief_engine.py::test_long_predict_update_chain_stable_normalized` |
| After false search, mass removed and renormalized | `tests/test_belief_engine.py::test_false_search_feedback_zeroes_location` |

Implementation: [`3600-agents/Yolanda/belief.py`](3600-agents/Yolanda/belief.py) `_normalize()` with uniform fallback if the sum is non-positive.

## 2. Respawn / capture reset parity

Assignment intent: after a successful rat capture, belief matches one step of probability mass at `(0,0)` followed by `1000` rat transitions—equivalently `e_0 @ T^1000` for the runtime row-stochastic `T`.

| Check | Test |
| --- | --- |
| Cached `reset_prior` matches `e_0 @ T^1000` for **non-identity** `T` | `tests/test_belief_engine.py::test_reset_prior_parity_non_identity_transition` |
| `reset_after_capture()` equals cached `reset_prior` | `tests/test_belief_engine.py::test_reset_after_capture_matches_cached_prior` |
| `apply_search_feedback(..., True)` resets to `reset_prior` | `tests/test_belief_engine.py::test_true_search_feedback_matches_reset_prior` |
| Channel + tri-state integration | `tests/test_policy_contract.py::test_apply_search_channels_obeys_tri_state_and_deduplicates` |

## 3. Runtime transition matrix discipline

[`3600-agents/Yolanda/agent.py`](3600-agents/Yolanda/agent.py) passes the engine-provided `transition_matrix` into `BeliefEngine` only. No static `.pkl` or baked matrix is used for updates, matching per-game perturbation semantics in the spec and `bot_plan_v4.md`.

## 4. Search EV (`§10.6`)

| Rule | Test |
| --- | --- |
| `EV(c) = 6 * P(c) - 2` | `tests/test_policy_contract.py::test_score_search_is_six_p_minus_two` |
| Positive EV iff `P(c) > 1/3` (numerical sanity) | `tests/test_policy_contract.py::test_score_search_positive_ev_threshold_one_third` |

Implementation: [`3600-agents/Yolanda/policy.py`](3600-agents/Yolanda/policy.py) `score_search`.

## 5. Search precision vs random-search baseline

**Baseline:** [`3600-agents/RandomSearchBaseline/`](3600-agents/RandomSearchBaseline/) — identical belief update and candidate generation as Yolanda, but the chosen search cell is **uniform** among legal search candidates when a search action is selected.

**Harness:** [`workflows/m1_search_precision_batch.py`](workflows/m1_search_precision_batch.py). Uses **`play_time=240`** via `play_game(..., play_time_override=240)` for the strict clock budget. On Linux, run with `--limit-resources` to match the full restricted tournament profile; on macOS the default is `--no-limit-resources` because `RLIMIT_RSS` setup often fails locally (still **240s** budget).

**Sample run (repository dev machine, `limit_resources=False`, 12 games, seed 42):**

| Agent | Search attempts | Correct | Precision |
| --- | ---:| ---:| ---:|
| Yolanda | 297 | 89 | 0.300 |
| RandomSearchBaseline | 363 | 13 | 0.036 |

Yolanda search precision is **above** the random-search baseline on this sample, satisfying the M1 acceptance gate for improved search targeting under shared timing and candidate structure.

## 6. Verification commands

```bash
PYTHONPATH=engine:3600-agents .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python workflows/quality_guard.py
# Optional M1 batch (increase --games for smoother estimates):
.venv/bin/python workflows/m1_search_precision_batch.py --games 12 --seed-start 42
```

On Linux for restricted-mode parity:

```bash
.venv/bin/python workflows/m1_search_precision_batch.py --games 12 --limit-resources
```
