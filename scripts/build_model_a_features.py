"""Build the Model A feature table from score_trends + model_a_candidates. 0 AniList requests.

Run from the episode-three folder:
    python -m scripts.build_model_a_features

Steps (safe to re-run; the output is identical):
1. Python computes one model_a_snapshots document per eligible show (markers, ep1/ep3 snapshots, features,
   label, ledger) and writes the ledger onto model_a_candidates (model_a_status, model_a_reasons).
2. A MongoDB aggregation ($lookup, $project, $set, $merge) writes model_a_features.
3. reports/model_a_data_funnel.md is rewritten (deterministic).
"""
import sys
from collections import Counter
from pathlib import Path

# Lets "python scripts\build_model_a_features.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import ASCENDING, ReplaceOne, UpdateOne

from episode_three import anilist_sync, config, db
from episode_three.collect import score_trends as trends
from episode_three.features import model_a
from episode_three.features import model_a_pipeline as pipeline


def load(database):
    candidates = list(database[pipeline.CANDIDATES].find({}))
    w1, w2 = {}, {}
    for doc in database[trends.COLLECTION].find({}, {"snapshots_w1": 1, "snapshots_w2": 1}):
        w1[doc["_id"]], w2[doc["_id"]] = doc.get("snapshots_w1", []), doc.get("snapshots_w2", [])
    return candidates, w1, w2


def write_snapshots_and_ledger(database, documents):
    ids = [d["_id"] for d in documents]
    database[pipeline.SNAPSHOTS].bulk_write([ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in documents], ordered=False)
    database[pipeline.SNAPSHOTS].delete_many({"_id": {"$nin": ids}})
    database[pipeline.CANDIDATES].bulk_write([UpdateOne({"_id": d["_id"]}, {"$set": {
        "model_a_status": d["status"], "model_a_reasons": d["reasons"], "model_a_subreasons": d["subreasons"]}})
        for d in documents], ordered=False)


def run_pipeline(database, documents):
    trainable = [d["_id"] for d in documents if d["status"] == "trainable"]
    database[pipeline.SNAPSHOTS].aggregate(pipeline.features_pipeline())   # the $merge stage writes the output
    database[pipeline.FEATURES].delete_many({"_id": {"$nin": trainable}})   # a show that is no longer trainable goes
    database[pipeline.FEATURES].create_index([("split", ASCENDING)])
    return trainable


def print_summary(documents, features):
    by_split = Counter(f["split"] for f in features)
    print(f"\nEligible shows: {len(documents)}; trainable: {len(features)} "
          f"(train {by_split['train']}, validation {by_split['validation']}, test {by_split['test']})")
    first = Counter(d["reasons"][0] for d in documents if d["reasons"])
    print(f"Excluded: {sum(first.values())}, by first reason:")
    for reason, count in sorted(first.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {reason:<22} {count:>5}")
    print("(0 AniList requests used.)")


def main():
    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)
    candidates, w1, w2 = load(database)
    documents = model_a.build_all(candidates, w1, w2)
    write_snapshots_and_ledger(database, documents)
    run_pipeline(database, documents)
    features = list(database[pipeline.FEATURES].find({}, {"split": 1, "season": 1, "season_year": 1}))
    model_a.assert_splits_disjoint({f["_id"]: f["split"] for f in features},
                                   {f["_id"]: (f["season_year"], f["season"]) for f in features})
    print_summary(documents, features)


if __name__ == "__main__":
    try:
        main()
    except config.ConfigError as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nStopped: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
