# 014 — Model A final evaluation on the locked test set (Phase 6, step 3)

- **Date:** 2026-10-19
- **Task:** TASK 014 from the instructor (spec v1.12 → v1.13). **0 AniList requests.** The test split was loaded exactly once.
- **Status:** Done. **PASS, narrowly** (10.01% below B1 against a 10% bar). Phase 6 closed.

## Summary

Alpha was settled before the lock (alpha 100 is an interior CV optimum). The plan was committed as a pre-registration lock, then the Ridge pipeline and the baselines were refitted on train + validation (873 shows) and scored once on the 337 test shows.

## Files changed (one commit each)

| Commit | What |
|---|---|
| `11cfe4a`, `db317d6` | `--extend-ridge-alpha` and its result in `model_a_selection_v1.json` |
| `cd2912a` | `final_a.py`: lock build and check, run-once guard, refit, evaluation, report rendering; `lock_model_a_test.py` |
| `c3067c0` | `reports/model_a_test_lock.json` (the pre-registration; test split not loaded) |
| `e4f255d` | `scripts/evaluate_model_a_final.py` (the only caller of the allow_test flag) with `--rehearsal` (validation, writes nothing) |
| `b1913b0` | `reports/model_a_v1.json`, `model_a_v1.md` |

## Result (337 test shows)

| Model | MAE [95% CI] | RMSE | within ±3 |
|---|---|---|---|
| B1 finale = ep3 | 1.69 [1.53, 1.85] | 2.27 | 89.3% |
| B2 mean (68.52) | 7.11 [6.59, 7.62] | 8.59 | 24.9% |
| B3 linear (−3.08 + 1.0485 × ep3) | 1.70 [1.54, 1.85] | 2.25 | 84.3% |
| **Ridge (alpha 100)** | **1.52 [1.38, 1.66]** | 2.01 | 88.4% |

Paired Ridge − B1: −0.169 [−0.273, −0.059]; Ridge − B3: −0.179 [−0.275, −0.071]. Criterion: 1.5194 vs 1.6884 = **10.01% lower → PASS** (margin 0.01 percentage points).

## Sensitivity (descriptive)

- Per season, Ridge vs B1 MAE: Winter 2025 1.69/1.72, Spring 2025 1.80/1.95, Summer 2025 1.15/1.31, Fall 2025 1.59/1.81, Winter 2026 1.48/1.50, Spring 2026 1.61/1.75, Summer 2026 1.41/1.83. Ridge never loses.
- TV 1.50 vs 1.67; ONA 1.71 vs 1.82; sequels 1.52 vs 1.79; non-sequels 1.52 vs 1.65.
- Without flagged shows: 1.50–1.52 vs 1.67–1.69 (8 shows flagged in total).
- Secondary label (324 shows): Ridge 2.66, B1 2.82.
- Ten largest Ridge errors (guesses at causes, nothing changed): One Punch Man 3 (ep3 70, predicted 66.6, label 54; a hyped sequel whose score collapsed after audience backlash, unpredictable from early data); Maebashi Witches (56 → 61), Gnosia (69 → 76), Hell Mode (64 → 68), Baban Baban Ban Vampire (52 → 57) all rose later (scores at the low end drift up); TRIGUN STARGAZE (73 → 69), Shin Samurai-den YAIBA (74 → 70), Nanoha EXCEEDS (68 → 64), Otonari no Tenshi-sama 2nd Season (80 → 76), Shibou Yuugi (78 → 74) all fell (fan-inflated or high ep3 scores regress). Mostly regression to the mean; only one true outlier.

## Honest caveats

1. The pass is razor-thin: the 10% bar was cleared by 0.0127 percentage points, so a slightly different test sample could flip it. The paired CI shows the improvement is real (entirely below 0) but its size is uncertain.
2. Ridge's within-±3 share is slightly below B1's (88.4% vs 89.3%): the gain is fewer big misses, not more near-exact ones.
3. Test MAE is lower than validation for every model (B1 1.69 vs 1.95): the test seasons are easier, not the model better.

## Notes

- Nirav's re-run of `--extend-ridge-alpha` only refreshed `code_commit` inside that block (same numbers); committed with the results.
- The guard worked: the second evaluation stopped with "already evaluated".
