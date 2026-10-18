"""Offline tests for episode_three/models/metrics.py and data_a.py."""
import math

import pytest

from episode_three.models import data_a, metrics


# --- metrics, with hand-computed answers -------------------------------------------------------------------

Y_TRUE, Y_PRED = [70, 80, 90], [72, 80, 87]       # misses: 2, 0, 3


def test_mae_rmse_and_within():
    assert metrics.mae(Y_TRUE, Y_PRED) == pytest.approx(5 / 3)                  # (2 + 0 + 3) / 3
    assert metrics.rmse(Y_TRUE, Y_PRED) == pytest.approx(math.sqrt(13 / 3))     # sqrt((4 + 0 + 9) / 3)
    assert metrics.pct_within(Y_TRUE, Y_PRED, k=3) == 100.0                     # a miss of exactly 3 counts
    assert metrics.pct_within(Y_TRUE, Y_PRED, k=2) == pytest.approx(200 / 3)    # 2 of 3 shows
    assert metrics.pct_within(Y_TRUE, Y_PRED, k=1) == pytest.approx(100 / 3)
    assert metrics.mae([5, 5], [5, 5]) == 0 and metrics.rmse([5, 5], [5, 5]) == 0


def test_metrics_reject_bad_input():
    with pytest.raises(ValueError):
        metrics.mae([1, 2], [1])
    with pytest.raises(ValueError):
        metrics.rmse([], [])


def test_bootstrap_is_reproducible_and_brackets_the_estimate():
    y_true = [60 + (i * 7) % 30 for i in range(80)]
    y_pred = [70] * 80
    low, high = metrics.bootstrap_ci(metrics.mae, y_true, y_pred)
    assert (low, high) == metrics.bootstrap_ci(metrics.mae, y_true, y_pred)       # same seed, same answer
    assert low < metrics.mae(y_true, y_pred) < high
    assert metrics.bootstrap_ci(metrics.mae, y_true, y_pred, seed=1) != (low, high)  # another seed wobbles
    assert metrics.bootstrap_ci(metrics.mae, [70] * 10, [72] * 10) == (2.0, 2.0)     # no spread, no interval
    # more shows -> a narrower interval
    wide = metrics.bootstrap_ci(metrics.mae, y_true[:20], y_pred[:20])
    assert (wide[1] - wide[0]) > (high - low)


# --- the loader ---------------------------------------------------------------------------------------------

class ExplodingDatabase:
    """Any use of it fails the test: proves the lock is checked before the database is touched."""
    def __getitem__(self, name):
        raise AssertionError("the database must not be touched")


def doc(number, split, season_year, season, score=70):
    return {"_id": f"anilist:{number}", "split": split, "season": season, "season_year": season_year,
            "features": {"ep3_score": score, "format": "TV"}, "label": {"score": score + 1, "offset_days": 0, "secondary_score": None},
            "flags": {"m1_unknown": False}}


def test_loader_refuses_the_test_split():
    for splits in (("test",), ("train", "test"), ("train", "validation", "test")):
        with pytest.raises(data_a.TestSplitLocked):
            data_a.load_model_a(splits, database=ExplodingDatabase())
    with pytest.raises(ValueError):
        data_a.load_model_a(("train", "nonsense"), database=ExplodingDatabase())


def test_loader_asks_the_database_only_for_the_requested_splits():
    asked = {}

    class Cursor(list):
        def sort(self, *args):
            return self

    class Collection:
        def find(self, query):
            asked.update(query)
            return Cursor()

    class Database:
        def __getitem__(self, name):
            assert name == data_a.FEATURES
            return Collection()

    assert data_a.load_documents(database=Database()) == []
    assert asked == {"split": {"$in": ["train", "validation"]}}      # "test" is never in the query


def test_frames_have_features_label_and_flags():
    frames = data_a.to_frames([doc(1, "train", 2023, "FALL"), doc(2, "validation", 2024, "WINTER", 75)])
    assert set(frames) == {"train", "validation"}
    row = frames["validation"].iloc[0]
    assert (row["_id"], row["ep3_score"], row["y"], row["format"]) == ("anilist:2", 75, 76, "TV")
    assert row["m1_unknown"] == False   # noqa: E712 (numpy bool)


def test_splits_must_be_disjoint_by_show_and_by_season():
    with pytest.raises(AssertionError, match="both"):
        data_a.to_frames([doc(1, "train", 2023, "FALL"), doc(1, "validation", 2024, "WINTER")])
    with pytest.raises(AssertionError, match="season"):
        data_a.to_frames([doc(1, "train", 2024, "WINTER"), doc(2, "validation", 2024, "WINTER")])
    data_a.to_frames([doc(1, "train", 2024, "WINTER"), doc(2, "train", 2024, "WINTER")])   # the same split may repeat a season


def test_fingerprint_depends_on_the_data_not_the_order():
    a, b = doc(1, "train", 2023, "FALL"), doc(2, "train", 2023, "FALL", 80)
    assert data_a.data_fingerprint([a, b]) == data_a.data_fingerprint([b, a])
    changed = dict(b, label={"score": 99, "offset_days": 0, "secondary_score": None})
    assert data_a.data_fingerprint([a, b]) != data_a.data_fingerprint([a, changed])
