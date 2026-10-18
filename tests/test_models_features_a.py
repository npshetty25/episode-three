"""Offline tests for episode_three/models/features_a.py."""
import numpy as np
import pandas as pd
import pytest

from episode_three.models import features_a


def frame(n=6, **overrides):
    data = {"_id": [f"anilist:{i}" for i in range(n)], "ep3_score": [70.0 + i for i in range(n)],
            "ep1_score": [68.0 + i for i in range(n)], "score_delta_1_3": [2.0] * n,
            "ep3_popularity": [1000 * (i + 2) for i in range(n)], "ep3_popularity_season_pct": [10.0 * i for i in range(n)],
            "ep3_popularity_vs_prev_season": [0.5 + i / 10 for i in range(n)], "popularity_growth_1_3": [1.5] * n,
            "ep3_in_progress": [100 * (i + 1) for i in range(n)], "episodes_planned": [12] * n,
            "prequel_finale_score": [None] * n, "is_sequel": [False] * n, "prequel_score_known": [False] * n,
            "format": ["TV"] * n, "source_material": ["MANGA"] * n, "genres": [["Action", "Drama"]] * n,
            "y": [72.0 + i for i in range(n)]}
    data.update(overrides)
    return pd.DataFrame(data)


def test_build_xy_columns_and_the_delta_round_trip():
    df = frame()
    X, y_delta, y = features_a.build_xy(df)
    assert list(X.columns) == features_a.INPUT_COLUMNS
    assert list(y_delta) == [2.0] * 6                           # finale - ep3
    assert list(X["ep3_score"] + y_delta) == list(y) == list(df["y"])   # ep3 + delta = label
    assert X["popularity"].iloc[0] == pytest.approx(np.log1p(2000))       # raw variant is log1p
    assert X["ep3_in_progress"].iloc[0] == pytest.approx(np.log1p(100))
    assert np.isnan(X["prequel_finale_score"]).all() and X["is_sequel"].dtype == float


def test_popularity_variants_pick_the_right_source_column():
    df = frame()
    assert list(features_a.build_xy(df, "season_pct")[0]["popularity"]) == [10.0 * i for i in range(6)]
    assert features_a.build_xy(df, "vs_prev")[0]["popularity"].iloc[2] == pytest.approx(0.7)
    with pytest.raises(ValueError):
        features_a.build_xy(df, "nonsense")


def test_missing_values_and_categories_are_handled():
    df = frame(source_material=[None, "MANGA", "MANGA", "MANGA", "MANGA", "MANGA"],
               ep1_score=[None, 68.0, 69.0, 70.0, 71.0, 72.0])
    X, _, _ = features_a.build_xy(df)
    assert X["source_material"].iloc[0] == "UNKNOWN" and np.isnan(X["ep1_score"].iloc[0])


def test_genre_vocabulary_comes_from_fit_rows_only_and_unseen_genres_are_ignored():
    train = pd.DataFrame({"genres": [["Action", "Drama"], ["Comedy"], []]})
    transformer = features_a.GenreMultiHot().fit(train)
    assert transformer.vocabulary_ == ["Action", "Comedy", "Drama"]
    later = pd.DataFrame({"genres": [["Action", "Horror"], ["Comedy", "Drama"], None]})   # Horror was never seen
    matrix = transformer.transform(later)
    assert matrix.shape == (3, 3) and "Horror" not in transformer.vocabulary_
    assert matrix.tolist() == [[1, 0, 0], [0, 1, 1], [0, 0, 0]]
    assert list(transformer.get_feature_names_out()) == ["genre_Action", "genre_Comedy", "genre_Drama"]


def test_preprocessor_is_fitted_on_the_given_rows_only():
    df = frame(12)
    train, other = df.iloc[:8], df.iloc[8:].copy()
    other["genres"] = [["Horror"]] * 4                      # a genre absent from train
    other["format"] = "ONA"                                  # a format absent from train
    X_train, _, _ = features_a.build_xy(train)
    X_other, _, _ = features_a.build_xy(other)
    prep = features_a.make_preprocessor().fit(X_train)
    names = list(prep.get_feature_names_out())
    assert "genres__genre_Horror" not in names and "cat__format_ONA" not in names
    out = prep.transform(X_other)
    assert out.shape[0] == 4 and out.shape[1] == len(names) and not np.isnan(out).any()
    assert not prep.transform(X_other)[:, [names.index("cat__format_TV")]].any()   # unseen format: all zeros


def test_imputer_uses_train_medians_and_adds_indicators():
    train = frame(6, ep1_score=[60.0, 70.0, 80.0, None, 90.0, 100.0])
    test = frame(2, ep1_score=[None, 50.0])
    prep = features_a.make_preprocessor().fit(features_a.build_xy(train)[0])
    names = list(prep.get_feature_names_out())
    out = prep.transform(features_a.build_xy(test)[0])
    assert out[0, names.index("num__ep1_score")] == 80.0                       # median of the TRAIN values
    assert out[0, [i for i, n in enumerate(names) if n.startswith("num__missingindicator")][0]] == 1.0


def test_scaling_only_when_asked():
    X, _, _ = features_a.build_xy(frame(8))
    scaled = features_a.make_preprocessor(scale=True).fit_transform(X)
    plain = features_a.make_preprocessor(scale=False).fit_transform(X)
    names = list(features_a.make_preprocessor().fit(X).get_feature_names_out())
    column = names.index("num__ep3_score")
    assert abs(scaled[:, column].mean()) < 1e-9 and plain[:, column].mean() > 50
