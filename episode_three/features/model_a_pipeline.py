"""The MongoDB aggregation that turns model_a_snapshots into model_a_features.

Python computes the per-show results (snapshot rules are pure functions, spec v1.6 ruling 3). The pipeline then
does the reshape inside MongoDB: join the candidate metadata ($lookup), pick the columns ($project), assign the
time-based split ($set) and write the result ($merge, keyed by _id, so a re-run replaces the same documents and
gives identical output). Only fields named in $project reach model_a_features, so no current_* field and no
other label data can slip in by accident.
"""
from episode_three.features import model_a

SNAPSHOTS = "model_a_snapshots"
FEATURES = "model_a_features"
CANDIDATES = "model_a_candidates"


def split_expression():
    return {"$switch": {
        "branches": [
            {"case": {"$lte": ["$season_year", model_a.TRAIN_LAST_YEAR]}, "then": "train"},
            {"case": {"$eq": ["$season_year", model_a.VALIDATION_YEAR]}, "then": "validation"},
        ],
        "default": "test"}}


def features_pipeline():
    """The aggregation run on model_a_snapshots; its last stage writes model_a_features."""
    return [
        {"$match": {"status": "trainable"}},
        {"$lookup": {"from": CANDIDATES, "localField": "_id", "foreignField": "_id", "as": "candidate"}},
        {"$unwind": "$candidate"},
        {"$project": {
            "season": 1, "season_year": 1, "title": "$candidate.title",
            "features": {"$mergeObjects": ["$features", {
                "episodes_planned": "$candidate.episodes", "format": "$candidate.format",
                "source_material": "$candidate.source_material", "genres": "$candidate.genres"}]},
            "label": {"score": "$label.score", "date": "$label.date", "offset_days": "$label.offset_days",
                      "offset_unusual": "$label.offset_unusual", "secondary_score": "$secondary_score"},
            "flags": 1}},
        {"$set": {"split": split_expression()}},
        {"$merge": {"into": FEATURES, "on": "_id", "whenMatched": "replace", "whenNotMatched": "insert"}},
    ]
