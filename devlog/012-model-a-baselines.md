# 012 — Model A evaluation harness + baselines (Phase 6, step 1)

- **Date:** 2026-10-19
- **Task:** TASK 012 from the instructor (spec v1.10 → v1.11). **0 AniList requests.** Validation only: the test split was never loaded.
- **Status:** Done.

## Summary

The code that every later model will be judged by: a loader that refuses the test split, metric functions with hand-computed tests, three baselines, and a deterministic JSON report with a bootstrap confidence interval. Two earlier rules were corrected first.

## Files changed (one commit each)

| Commit | What |
|---|---|
| `8853816` | scikit-learn 1.9.0 installed and pinned (numpy 2.5.3 unchanged; pip check clean) |
| `7fdc9b5` | `label_offset_unusual` = offset not in {-1, 0, +1} (8 shows); funnel report rebuilt |
| `33e1795` | ledger: binge shows are `m3_not_before_m4 (binge)` before the missing-markers check (my TASK 011 mislabel) |
| `50db5a4` | `models/data_a.py` (loader, test lock, disjointness, fingerprint) and `models/metrics.py` |
| `72f1a91` | baselines B1/B2/B3, report builder, `evaluate_model_a_baselines`, tests |
| next | `reports/model_a_baselines_v1.json` |

## Results (validation, 192 shows)

| Baseline | MAE [95% CI] | RMSE | within ±3 |
|---|---|---|---|
| B1 finale = ep3 score | 1.95 [1.69, 2.21] | 2.66 | 83.9% |
| B2 train mean (68.41) | 6.81 [6.02, 7.63] | 8.96 | 38.0% |
| B3 linear: −3.7467 + 1.0587 × ep3 | 1.98 [1.73, 2.25] | 2.69 | 79.7% |

Train MAE: B1 1.99, B2 7.71, B3 1.96. B1 by format: TV 1.92 (179), ONA 2.38 (13). Sequels 1.79 (53), non-sequels 2.01 (139). Without marker_disagreement 1.93 (2 flagged, MAE 3.50), without label_offset_unusual 1.93 (3 flagged, 3.33), without m1_unknown 1.96 (3 flagged, 1.00), without any of the three 1.93 (7 flagged, 2.43). Descriptive only.

The episode-3 score is already a very strong signal (MAE under 2 points). B3 cannot beat B1 beyond noise on validation. A model must reach about 1.75 to clear the "10% below B1" bar.

## Why `no_ep1_4_trends` had 30 shows

It means M(3) or M(4) is unknown after combining the schedule AND the trend markers. All 30 were fallback-window shows (no schedule markers). 19 of them are binge releases (start date = end date): TASK 009 counted them as `m3_not_before_m4 (binge)`, so its `no_m3`/`no_m4` numbers (4 + 7 = 11) did not include them. TASK 011's ledger checked "markers missing" before "binge", so it mislabelled them; fixed in `33e1795`. Now: `m3_not_before_m4` 25 (19 binge + 6 same-day) and `no_ep1_4_trends` 11 (4 no M(3), 2 no M(4), 5 neither). 10 of the 30 do have some trend episode number in 1-4, but not both 3 and 4.

## Deviations from the task text (flagged)

1. `code_commit` = last commit touching code (not plain HEAD), else committing the report changes the next run.
2. `data_fingerprint` covers train + validation only, so no code path in this task reads test rows.
3. An extra commit for the binge ordering fix.

## Version conflicts

None. scikit-learn 1.9.0 requires numpy ≥ 1.26; numpy stayed at 2.5.3. Extra packages pulled in: scipy 1.18.1, joblib 1.6.0, threadpoolctl 3.7.0, narwhals 2.27.1, cloudpickle 3.1.2 (all pinned).
