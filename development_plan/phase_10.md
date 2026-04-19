## Objective
Produce full v4 release evidence package and finalize M4->Release promotion gates.

## Success Criteria
- Grade-alignment evidence for George/Albert/Carrie gates is documented (proxy + platform path).
- ELO trend and discrepancy-coverage evidence are documented.
- Final release checklist artifact is complete.

## Task List
- Create `development_plan/artifacts/m4_grade_alignment_pack.md` with gate evidence and external validation plan.
- Create `development_plan/artifacts/release_gate_checklist.md` mapping all v4 advancement-gate rows to proof artifacts.
- Re-audit contradiction/determinism/safety/stability checklist from v4 and capture outputs.

## Verification
- `python3 workflows/quality_guard.py`
- `python3 -m unittest discover -s tests -p "test_*.py"`

## Timebox
3.5h
