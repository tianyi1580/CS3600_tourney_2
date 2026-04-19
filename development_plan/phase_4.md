## Objective
Complete M1 integration of search EV and evidence-channel handling into action selection.

## Success Criteria
- Search scoring uses `EV = 6*P(c) - 2` and is compared deterministically against tactical options.
- Own/opponent search channels are applied safely with tri-state semantics.
- M1 artifact report is generated.

## Task List
- Integrate `score_search(...)` and normalized cross-family comparison logic.
- Ensure channel-driven belief updates handle `None` result values safely.
- Add tests for search EV threshold behavior and deterministic tie-break outputs.
- Create `development_plan/artifacts/m1_belief_report.md` with normalization/reset/search-parity evidence.

## Verification
- `python3 -m unittest tests/test_policy_contract.py`
- `python3 -m unittest discover -s tests -p "test_*.py"`
- `python3 workflows/quality_guard.py`

## Timebox
3.5h
