"""Turn the Model A frame into model inputs. Everything that learns from data lives inside the sklearn pipeline,
so it is fitted on a fold's TRAINING rows only (imputation medians, scaling, the category and genre vocabularies).

Target (instructor ruling a): delta = finale score - ep3 score. Prediction = ep3 score + predicted delta, clipped to [0, 100].
"""
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

POPULARITY_VARIANTS = {
    "raw": "log1p of ep3_popularity",
    "season_pct": "ep3_popularity_season_pct (percentile among same-season shows)",
    "vs_prev": "ep3_popularity_vs_prev_season (ratio to the previous season's median)",
}
NUMERIC = ["ep3_score", "ep1_score", "score_delta_1_3", "popularity", "popularity_growth_1_3", "ep3_in_progress",
           "episodes_planned", "prequel_finale_score", "is_sequel", "prequel_score_known"]
CATEGORICAL = ["format", "source_material"]
GENRES = "genres"
INPUT_COLUMNS = NUMERIC + CATEGORICAL + [GENRES]


def _number(series):
    return pd.to_numeric(series, errors="coerce").astype(float)


def popularity_column(df, variant):
    if variant == "raw":
        return np.log1p(_number(df["ep3_popularity"]))
    if variant == "season_pct":
        return _number(df["ep3_popularity_season_pct"])
    if variant == "vs_prev":
        return _number(df["ep3_popularity_vs_prev_season"])
    raise ValueError(f"unknown popularity variant {variant!r}; choose from {sorted(POPULARITY_VARIANTS)}")


def build_xy(df, popularity_variant="raw"):
    """(X, y_delta, y): X has INPUT_COLUMNS; y is the finale score; y_delta = y - ep3_score."""
    X = pd.DataFrame(index=df.index)
    for column in ("ep3_score", "ep1_score", "score_delta_1_3", "popularity_growth_1_3", "episodes_planned",
                   "prequel_finale_score"):
        X[column] = _number(df[column])
    X["popularity"] = popularity_column(df, popularity_variant)
    X["ep3_in_progress"] = np.log1p(_number(df["ep3_in_progress"]))
    X["is_sequel"] = df["is_sequel"].astype(float)
    X["prequel_score_known"] = df["prequel_score_known"].astype(float)
    for column in CATEGORICAL:
        X[column] = df[column].fillna("UNKNOWN").astype(str)
    X[GENRES] = df[GENRES].map(lambda g: list(g) if isinstance(g, (list, tuple)) else [])
    X = X[INPUT_COLUMNS]
    y = _number(df["y"])
    return X, y - X["ep3_score"], y


class GenreMultiHot(BaseEstimator, TransformerMixin):
    """A 0/1 column per genre. The vocabulary is learned in fit, from the rows given to fit ONLY;
    a genre never seen in fit is ignored when transforming (it gets no column)."""

    def fit(self, X, y=None):
        self.vocabulary_ = sorted({g for genres in self._lists(X) for g in genres})
        self._index = {g: i for i, g in enumerate(self.vocabulary_)}
        return self

    @staticmethod
    def _lists(X):
        column = X.iloc[:, 0] if hasattr(X, "iloc") else np.asarray(X)[:, 0]
        return [list(g) if isinstance(g, (list, tuple)) else [] for g in column]

    def transform(self, X):
        lists = self._lists(X)
        matrix = np.zeros((len(lists), len(self.vocabulary_)))
        for row, genres in enumerate(lists):
            for genre in genres:
                if genre in self._index:
                    matrix[row, self._index[genre]] = 1.0
        return matrix

    def get_feature_names_out(self, input_features=None):
        return np.array([f"genre_{g}" for g in self.vocabulary_], dtype=object)


def make_preprocessor(scale=False):
    """Numeric: median imputation + missing-indicator columns (+ standardising for Ridge); format and
    source_material: one-hot (unseen categories ignored); genres: multi-hot. Dense output."""
    steps = [("impute", SimpleImputer(strategy="median", add_indicator=True))]
    if scale:
        steps.append(("scale", StandardScaler()))
    return ColumnTransformer(
        [("num", Pipeline(steps), NUMERIC),
         ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
         ("genres", GenreMultiHot(), [GENRES])],
        sparse_threshold=0)
