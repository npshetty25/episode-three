# 013 — Model A candidates chosen on validation (Phase 6, step 2)

- **Date:** 2026-10-19
- **Task:** TASK 013 from the instructor (spec v1.11 → v1.12). **0 AniList requests.** The test split was never loaded.
- **Status:** Done. Chosen: **Ridge**, and it beats B1 under rule f.

## Summary

Three model families (Ridge, RandomForest, HistGradientBoosting) predict the *change* from the episode-3 score to the finale score. Hyperparameters and the popularity variant are chosen by expanding-window time CV inside train. The three tuned models are then compared once on validation against B1 and B3 with paired bootstrap CIs.

## Files changed (one commit each)

| Commit | What |
|---|---|
| `108f5d4` | `models/features_a.py`: `build_xy` (delta target, three popularity variants), `GenreMultiHot` (vocabulary from fit rows), `make_preprocessor` |
| `b4b7422` | `models/train_a.py`: `time_folds`, `tune_family` (refuses non-train rows), `fit_family`, `predict_finale` (clipped), the declared grids |
| `1a8c046` | `metrics.paired_bootstrap_ci` |
| `4ce2cc5` | `models/select_a.py` (selection, importance, printable lines), `models/run_info.py`, `scripts/train_model_a.py`, tests |
| next | `reports/model_a_selection_v1.json` |

## Results

Time-CV MAE on the finale score (mean of folds 2020 / 2021 / 2022 / 2023):

| Family | raw | season_pct | vs_prev | chosen |
|---|---|---|---|---|
| Ridge | **1.696** | 1.700 | 1.698 | raw, alpha 100 |
| RandomForest | 1.686 | 1.691 | **1.683** | vs_prev, leaf 5, max_features 0.33 |
| HGB | 1.794 | 1.788 | **1.776** | vs_prev, lr 0.03, 200 iter, 15 leaves |

Validation (192 shows):

| Model | MAE [95% CI] | RMSE | within ±3 | vs B1 (paired) | vs B3 (paired) |
|---|---|---|---|---|---|
| B1 | 1.95 [1.69, 2.21] | 2.66 | 83.9% | – | −0.034 [−0.113, +0.045] |
| B3 | 1.98 [1.73, 2.25] | 2.69 | 79.7% | +0.034 [−0.045, +0.113] | – |
| **Ridge** | **1.73 [1.51, 1.96]** | 2.34 | 84.4% | **−0.217 [−0.378, −0.063]** | −0.251 [−0.404, −0.110] |
| RandomForest | 1.76 [1.54, 2.00] | 2.39 | 85.9% | −0.184 [−0.345, −0.017] | −0.219 [−0.378, −0.069] |
| HGB | 1.84 [1.61, 2.09] | 2.51 | 83.3% | −0.105 [−0.305, +0.088] | −0.139 [−0.340, +0.045] |

Ridge's MAE is 11.2% below B1. 54 configurations (216 CV fits + 3 refits), runtime about 85 s.

Top-10 permutation importance (Ridge, validation, increase in finale MAE; descriptive only): score_delta_1_3 +0.198, ep3_score +0.051, genres +0.048, source_material +0.043, popularity +0.029, ep3_in_progress +0.018, is_sequel +0.012, episodes_planned +0.007, ep1_score +0.002, prequel_finale_score +0.001.

## Things worth noticing

1. **Ridge alpha = 100 is the top of the declared grid** (a boundary value). The optimum may be higher; the grid was pre-declared, so I did not extend it. A question for the instructor.
2. The three popularity variants differ by less than 0.02 MAE in CV: that is noise. They do not matter much here.
3. The strongest signal is `score_delta_1_3` (how much the score moved between episode 1 and 3), i.e. momentum, more than ep3_score itself (which is also the base of the prediction).
4. The simplest model (Ridge) won; HGB was worst. With ~680 training rows, regularised linear models are hard to beat.
5. Ridge and RandomForest differ by 0.03 MAE, well inside the noise; Ridge is chosen only because rule f says lowest validation MAE.
