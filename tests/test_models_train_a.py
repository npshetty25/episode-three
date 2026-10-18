"""Offline tests for episode_three/models/train_a.py (small synthetic data, fast)."""
import numpy as np
import pandas as pd
import pytest

from episode_three.models import features_a, train_a


def make_df(years=(2018, 2019, 2020, 2021, 2022, 2023), per_year=14, split="train", seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for year in years:
        for i in range(per_year):
            ep3 = float(rng.integers(55, 90))
            rows.append({"_id": f"anilist:{year}-{i}", "split": split, "season_year": year,
                         "season": ["WINTER", "SPRING", "SUMMER", "FALL"][i % 4], "ep3_score": ep3,
                         "ep1_score": ep3 - 1 if i % 5 else None, "score_delta_1_3": 1.0, "ep3_popularity": 3000 + 100 * i,
                         "ep3_popularity_season_pct": 7.0 * i, "ep3_popularity_vs_prev_season": 1.0 + i / 20,
                         "popularity_growth_1_3": 1.2, "ep3_in_progress": 500 + i, "episodes_planned": 12,
                         "prequel_finale_score": None, "is_sequel": bool(i % 3 == 0), "prequel_score_known": False,
                         "format": "TV" if i % 6 else "ONA", "source_material": "MANGA", "genres": [["Action"], ["Drama", "Comedy"]][i % 2],
                         "y": ep3 + 2 + rng.normal(0, 1)})
    return pd.DataFrame(rows)


def test_time_folds_never_train_on_a_later_year_than_they_score():
    df = make_df()
    folds = train_a.time_folds(df)
    assert len(folds) == 4
    for (train, test), year in zip(folds, train_a.FOLD_TEST_YEARS):
        assert set(df["season_year"].iloc[test]) == {year}
        assert df["season_year"].iloc[train].max() <= year - 1
        assert set(train).isdisjoint(test)
    first_train = df["season_year"].iloc[folds[0][0]]
    assert set(first_train) == {2018, 2019}                       # Fall 2018 (season_year 2018) is in the first fit set
    assert len(folds[3][0]) == 14 * 5                              # the last fold fits on 2018..2022


def test_the_search_refuses_validation_rows_and_only_sees_train_indices():
    df = make_df()
    with_validation = pd.concat([df, make_df(years=(2024,), split="validation")], ignore_index=True)
    with pytest.raises(ValueError, match="train split only"):
        train_a.tune_family("ridge", with_validation, "raw")
    # even the fold indices of a train-only frame stay inside it, and inside the years 2018-2023
    for train, test in train_a.time_folds(df):
        assert max(train.max(), test.max()) < len(df) and df["season_year"].iloc[np.r_[train, test]].max() <= 2023


def test_delta_target_round_trip_and_clipping():
    df = make_df()
    X, y_delta, y = features_a.build_xy(df)
    assert np.allclose(X["ep3_score"] + y_delta, y)

    class Constant:
        def __init__(self, value):
            self.value = value

        def predict(self, X):
            return np.full(len(X), self.value)

    assert np.allclose(train_a.predict_finale(Constant(0.0), X), X["ep3_score"])        # delta 0 -> finale = ep3
    assert np.allclose(train_a.predict_finale(Constant(5.0), X), (X["ep3_score"] + 5).clip(upper=100))
    assert train_a.predict_finale(Constant(500.0), X).max() == 100                       # clipped above
    assert train_a.predict_finale(Constant(-500.0), X).min() == 0                        # clipped below
    assert train_a.finale_mae_scorer(Constant(0.0), X, y_delta) == pytest.approx(-float(np.mean(np.abs(y_delta))))


def test_grids_are_small_and_as_declared():
    assert [train_a.n_configurations(f) for f in train_a.FAMILIES] == [4, 6, 8]
    assert all(train_a.n_configurations(f) <= 12 for f in train_a.FAMILIES)
    assert train_a.GRIDS["rf"]["model__max_features"] == [0.33, 1.0]
    rf = train_a.make_estimator("rf")
    assert (rf.n_estimators, rf.random_state) == (500, 42)
    hgb = train_a.make_estimator("hgb")
    assert (hgb.l2_regularization, hgb.early_stopping, hgb.random_state) == (1.0, False, 42)


@pytest.mark.parametrize("family", ["ridge", "hgb"])
def test_tuning_returns_cv_results_for_every_configuration_and_fit_predict_works(family):
    df = make_df()
    result = train_a.tune_family(family, df, "raw")
    assert len(result["results"]) == train_a.n_configurations(family)
    assert len(result["per_fold"]) == 4 and result["best_cv_mae"] == pytest.approx(np.mean(result["per_fold"]))
    assert result["best_cv_mae"] == min(r["mean_cv_mae"] for r in result["results"])
    assert result["best_cv_mae"] < 3                                   # the synthetic delta is ~ +2: learnable
    model = train_a.fit_family(family, result["best_params"], "raw", df)
    X, _, _ = features_a.build_xy(df)
    predictions = train_a.predict_finale(model, X)
    assert predictions.shape == (len(df),) and predictions.min() >= 0 and predictions.max() <= 100


def test_tuning_is_deterministic():
    df = make_df()
    first, second = train_a.tune_family("ridge", df, "season_pct"), train_a.tune_family("ridge", df, "season_pct")
    assert first == second
