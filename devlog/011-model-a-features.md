# 011 — Model A feature pipeline (Phase 5, step 5)

- **Date:** 2026-10-19
- **Task:** TASK 011 from the instructor (spec v1.9 → v1.10). **0 AniList requests.**
- **Status:** Done. 1,210 trainable shows (instructor expected 1,100–1,250).

## Summary

One feature row per trainable show, a recorded reason for every show that is not trainable, a time-based split, and tests that features never read label data. Python holds the rules as pure functions; MongoDB does the reshape and the write.

## Files changed (one commit each)

| Commit | What |
|---|---|
| `08c6884` | `features/model_a.py`: `final_markers`, floored `select_snapshot`, `floor_impact`, primary label with offset; tests |
| `5cb7acd` | features (ep1/ep3, prequel, two popularity normalisations), the ledger, `build_all`; tests incl. leakage and ledger completeness |
| `b76b91c` | aggregation pipeline (`$lookup` → `$project` → `$set` split → `$merge`) and `scripts/build_model_a_features.py` |
| `cf69536` | funnel report, `diagnose_ep3_window`, `check_db` now lists collections |

## Results

- Eligible 1,431 → trainable **1,210**: train 681, validation 192, test 337.
- Excluded 221 by first reason: ep3_popularity_low 85, no_w1_records 54, no_ep3_snapshot 31, no_ep1_4_trends 30, no_primary_label 15, m3_not_before_m4 6.
- Floor impact: ep3 narrowed 1 (lost 1); ep1 narrowed 5 (lost 1).
- K = 6 diagnosis: 0 of the 31 rescued (30 have no scored record at all, 1 was lost to the floor).
- Nulls: vs_prev_season 26 (all Fall 2018), season_pct 0, ep1_score 127.
- Prequel dropped by the date rule: 15 shows. Split label means 68.41 / 68.91 / 68.89.
- 153 tests pass offline. Database 25.5 MB of 512.

## Decisions I made where the task text was silent

The task refers to "the rulings above" (floored windows, K = 3, label_offset, trainability), which were not in the text I received. I implemented what the task states and assumed the rest; all assumptions are in spec v1.10:

1. `label_offset_unusual` = offset is not 0 (my TASK 010 proposal).
2. The ep3 popularity filter is the spec's 2,000.
3. A show can have several exclusion reasons; the first in funnel order is its funnel step.
4. ONA is not excluded as a class; `binge` is a sub-reason of `m3_not_before_m4`.
5. Percentile and previous-season median use shows with an ep3 snapshot and popularity ≥ 2,000.

## Questions for the instructor

1. Is "offset != 0" the right `label_offset_unusual` rule (93 of 1,210 flagged), or should +1 count as usual?
2. 15 prequels were dropped by the date rule; several are consecutive ids (e.g. 139213 / 139212), i.e. split-cour sequels starting before the prequel's finale. Keep as null?
3. 127 trainable shows have no ep1 features (55 no scored record, 37 M(1) not before M(2), 32 M(1) unknown, 3 empty window). Fine as nulls for Phase 6?
