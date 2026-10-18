"""Load the Model A feature table as pandas DataFrames, one per split.

The test split is locked: asking for it without allow_test=True raises TestSplitLocked BEFORE the database is
touched, and the query only ever names the requested splits. TASK 014 (the one final evaluation) passes
allow_test=True; nothing before it should.
"""
import hashlib
import json

import pandas as pd

from episode_three import config, db

FEATURES = "model_a_features"
SPLITS = ("train", "validation", "test")
DEFAULT_SPLITS = ("train", "validation")


class TestSplitLocked(Exception):
    """Raised when the test split is requested without allow_test=True."""
    __test__ = False   # not a pytest test class


def load_documents(splits=DEFAULT_SPLITS, allow_test=False, database=None):
    """The model_a_features documents of the requested splits, sorted by _id."""
    splits = tuple(splits)
    unknown = set(splits) - set(SPLITS)
    if unknown:
        raise ValueError(f"unknown split(s): {sorted(unknown)}")
    if "test" in splits and not allow_test:
        raise TestSplitLocked("The test split is locked until the final evaluation (TASK 014): pass allow_test=True there only.")
    database = database if database is not None else db.get_client()[config.MONGODB_DB]
    return list(database[FEATURES].find({"split": {"$in": list(splits)}}).sort("_id", 1))


def to_frames(documents):
    """{split: DataFrame}: one row per show; features as columns; the label is column y."""
    rows = []
    for doc in documents:
        row = {"_id": doc["_id"], "split": doc["split"], "season": doc["season"], "season_year": doc["season_year"],
               **doc["features"], "y": doc["label"]["score"], "y_secondary": doc["label"].get("secondary_score"),
               "label_offset_days": doc["label"]["offset_days"], **doc["flags"]}
        rows.append(row)
    frame = pd.DataFrame(rows)
    frames = {split: part.reset_index(drop=True) for split, part in frame.groupby("split", sort=False)} if rows else {}
    assert_disjoint(frames)
    return frames


def assert_disjoint(frames):
    """No show and no season appears in two splits."""
    seen_ids, seen_seasons = {}, {}
    for split, frame in frames.items():
        for show_id in frame["_id"]:
            assert show_id not in seen_ids, f"{show_id} is in both {seen_ids[show_id]} and {split}"
            seen_ids[show_id] = split
        for season in set(zip(frame["season_year"], frame["season"])):
            assert season not in seen_seasons or seen_seasons[season] == split, \
                f"season {season} is in both {seen_seasons[season]} and {split}"
            seen_seasons[season] = split


def load_model_a(splits=DEFAULT_SPLITS, allow_test=False, database=None):
    """{split: DataFrame} for the requested splits (train and validation by default)."""
    return to_frames(load_documents(splits, allow_test, database))


def data_fingerprint(documents):
    """sha256 over the given documents sorted by _id, keys sorted: the same data gives the same hash."""
    digest = hashlib.sha256()
    for doc in sorted(documents, key=lambda d: d["_id"]):
        digest.update(json.dumps(doc, sort_keys=True, default=str).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()
