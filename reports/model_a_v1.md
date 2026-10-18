# Model A v1: final test result

Ridge (alpha 100, popularity raw) predicts the change from the episode-3 score to the finale score. Fitted on 873 shows (Fall 2018 to Fall 2024), scored once on 337 test shows (Winter 2025 to Summer 2026).

| Model | MAE [95% CI] | RMSE | within ±3 |
|---|---|---:|---:|
| B1 | 1.69 [1.53, 1.85] | 2.27 | 89.3% |
| B2 | 7.11 [6.59, 7.62] | 8.59 | 24.9% |
| B3 | 1.70 [1.54, 1.85] | 2.25 | 84.3% |
| ridge | 1.52 [1.38, 1.66] | 2.01 | 88.4% |

Paired difference in absolute error (Ridge minus baseline): vs B1 -0.169 [-0.273, -0.059], vs B3 -0.179 [-0.275, -0.071].

**Criterion (test MAE at least 10% below B1): PASS.** Ridge 1.52 vs B1 1.69, 10.0% lower.

## README results row

| Model | Test MAE [95% CI] | B1 (finale = ep3) | Improvement | 10% criterion |
|---|---|---|---|---|
| Model A v1 (Ridge, alpha 100) | 1.52 [1.38, 1.66] | 1.69 | 10.0% | PASS |

Full numbers, the sensitivity tables and the ten largest errors are in `model_a_v1.json`.
Code commit `e4f255dfb6`, lock `cfa2cd9a843c`, run count 1.
