"""Train and tune the three Model A candidate families. Hyperparameters are chosen by expanding-window time CV
INSIDE the train split; validation rows never reach the search (tune_family refuses them).

Target (ruling a): delta = finale - ep3 score; prediction = ep3 score + predicted delta, clipped to [0, 100].
"""
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline

from episode_three.models import features_a

SEED = 42
RF_TREES = 500
FAMILIES = ("ridge", "rf", "hgb")
FOLD_TEST_YEARS = (2020, 2021, 2022, 2023)      # fit on every season_year before the scored year
GRIDS = {                                       # pre-declared (ruling d); parameter names are Pipeline names
    "ridge": {"model__alpha": [0.1, 1, 10, 100]},
    "rf": {"model__min_samples_leaf": [5, 10, 20], "model__max_features": [0.33, 1.0]},
    "hgb": {"model__learning_rate": [0.03, 0.1], "model__max_iter": [200, 500], "model__max_leaf_nodes": [15, 31]},
}


def n_configurations(family):
    count = 1
    for values in GRIDS[family].values():
        count *= len(values)
    return count


def make_estimator(family):
    if family == "ridge":
        return Ridge()
    if family == "rf":
        return RandomForestRegressor(n_estimators=RF_TREES, random_state=SEED, n_jobs=1)
    if family == "hgb":
        return HistGradientBoostingRegressor(l2_regularization=1.0, early_stopping=False, random_state=SEED)
    raise ValueError(f"unknown family {family!r}; choose from {FAMILIES}")


def make_pipeline(family):
    """Preprocessing and model in one Pipeline: every fit learns the preprocessing from the rows it is given only."""
    return Pipeline([("prep", features_a.make_preprocessor(scale=family == "ridge")), ("model", make_estimator(family))])


def time_folds(df):
    """[(train_positions, test_positions)] for the expanding-window CV (ruling b), by season_year.

    Fit on season_year <= Y-1, score season_year == Y, for Y = 2020..2023. Fall 2018 has season_year 2018, so it is
    in every fit set.
    """
    years = df["season_year"].to_numpy()
    folds = []
    for year in FOLD_TEST_YEARS:
        train, test = np.flatnonzero(years <= year - 1), np.flatnonzero(years == year)
        assert len(train) and len(test), f"fold for {year} is empty"
        assert years[train].max() < years[test].min(), "a fold would train on the year it scores"
        folds.append((train, test))
    return folds


def predict_finale(model, X):
    """ep3 score + predicted delta, clipped to [0, 100]."""
    return np.clip(X["ep3_score"].to_numpy(dtype=float) + model.predict(X), 0, 100)


def finale_mae_scorer(estimator, X, y_delta):
    """Negative MAE on the FINALE score (not on the delta): the scorer GridSearchCV maximises."""
    truth = X["ep3_score"].to_numpy(dtype=float) + np.asarray(y_delta, dtype=float)
    return -float(np.mean(np.abs(truth - predict_finale(estimator, X))))


def tune_family(family, train_df, popularity_variant):
    """Grid search with the time folds. Returns the best params, its per-fold MAE and every configuration's CV MAE."""
    if not (train_df["split"] == "train").all():
        raise ValueError("tune_family accepts the train split only: validation rows must never reach the search")
    X, y_delta, _ = features_a.build_xy(train_df, popularity_variant)
    folds = time_folds(train_df)
    search = GridSearchCV(make_pipeline(family), GRIDS[family], cv=folds, scoring=finale_mae_scorer,
                          refit=False, error_score="raise", n_jobs=1)
    search.fit(X, y_delta)
    results = []
    for i, params in enumerate(search.cv_results_["params"]):
        per_fold = [-search.cv_results_[f"split{k}_test_score"][i] for k in range(len(folds))]
        results.append({"params": params, "mean_cv_mae": float(np.mean(per_fold)), "per_fold": [float(v) for v in per_fold]})
    best = min(results, key=lambda r: r["mean_cv_mae"])      # ties go to the earlier configuration
    return {"family": family, "variant": popularity_variant, "best_params": best["params"],
            "best_cv_mae": best["mean_cv_mae"], "per_fold": best["per_fold"], "results": results}


def fit_family(family, params, popularity_variant, train_df):
    """Fit one configuration on train_df. Returns the fitted Pipeline (which predicts the delta)."""
    X, y_delta, _ = features_a.build_xy(train_df, popularity_variant)
    return make_pipeline(family).set_params(**params).fit(X, y_delta)
