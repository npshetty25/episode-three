"""Import the Kaggle sample into MongoDB as Model B training data (mal_user_lists). 0 AniList requests.

Run from the episode-three folder (after collect_model_b_anime):
    python -m scripts.import_kaggle_users

Steps: keep a row only if its MAL id maps to exactly one AniList TV, non-adult anime (model_b_anime / model_b_unmapped);
keep users with 20+ entries; split users 70/15/15; split each user's entries into history and target; write one document
per user (batches of 500; documents of users no longer in the set are deleted from this collection only); rewrite
reports/model_b_data_funnel.md. Safe to re-run: the content is identical. Stops if the database passes 350 MB.
"""
import sys
from collections import Counter
from pathlib import Path

# Lets "python scripts\import_kaggle_users.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from pymongo import ASCENDING, ReplaceOne

from episode_three import anilist_sync, config, db
from episode_three.collect import kaggle_import as ki
from episode_three.collect import model_b_anime as mba
from episode_three.features import tv_filters as tf
from scripts.profile_vs_training import drop_rate, labelled_entries

SAMPLE_PATH = PROJECT_ROOT / "data" / "processed" / "mal_sample_5k_seed42.parquet"
REPORT = PROJECT_ROOT / "reports" / "model_b_data_funnel.md"
COLLECTION = "mal_user_lists"
BATCH = 500
STOP_MB = 350


def db_stats(database):
    stats = database.command("dbStats", scale=1024 * 1024)
    return {key: stats[key] for key in ("dataSize", "storageSize", "indexSize", "totalSize") if key in stats}


def write_documents(database, docs):
    collection = database[COLLECTION]
    for start in range(0, len(docs), BATCH):
        batch = docs[start:start + BATCH]
        collection.bulk_write([ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in batch], ordered=False)
    collection.delete_many({"_id": {"$nin": [d["_id"] for d in docs]}})     # this job's own collection only
    collection.create_index([("split", ASCENDING)])


def nirav_line(database):
    anime_csv = pd.read_csv(config.get_mal_data_dir() / "anime.csv", na_values=["Unknown"], encoding="utf-8", usecols=["MAL_ID", "Type"])
    mal_type = dict(zip(anime_csv["MAL_ID"].astype(int), anime_csv["Type"]))
    titles = {t["_id"]: t for t in database["titles"].find({})}
    entries = list(database["my_entries"].find({"source": "anilist"}))
    return tf.nirav_comparison(entries, titles, mal_type, labelled_entries, drop_rate)


def print_funnel(total_rows, funnel, users_removed, rows_removed, docs):
    print(f"\nRows: {total_rows:,} in the sample")
    for step in funnel:
        detail = (" " + str(step["subs"])) if step["subs"] else ""
        print(f"  - {step['reason']:<18} {step['rows_removed']:>8,}  -> {step['rows_after']:>9,} left{detail}")
    print(f"  - users below {ki.MIN_ENTRIES} entries ({users_removed} users) {rows_removed:>5,} rows -> {sum(d['n_entries'] for d in docs):,} kept")
    print(f"\nUsers kept: {len(docs):,}")
    print(f"  {'split':<11}{'users':>7}{'history':>10}{'target':>9}{'target drop':>13}   entries/user min / median / max")
    for name, s in ki.split_statistics(docs).items():
        print(f"  {name:<11}{s['users']:>7,}{s['history_rows']:>10,}{s['target_rows']:>9,}{100 * s['target_drop_rate']:>12.2f}%   "
              f"{s['entries_min']} / {s['entries_median']:g} / {s['entries_max']}")


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)
    before = db_stats(database)

    sample = pd.read_parquet(SAMPLE_PATH)
    docs_b = list(database[mba.COLLECTION].find({}, {"mal_id": 1, "anilist_id": 1, "format": 1, "is_adult": 1}))
    unmapped = [d["mal_id"] for d in database[mba.UNMAPPED].find({}, {"mal_id": 1})]
    anime_map = ki.classify_anime(docs_b, unmapped)
    kept, funnel = ki.apply_filters(sample, anime_map)
    kept, users_removed, rows_removed = ki.filter_users(kept)
    docs = ki.build_documents(kept)
    splits = {d["_id"]: d["split"] for d in docs}
    assert len(splits) == len(docs), "a user is in two splits"
    print_funnel(len(sample), funnel, users_removed, rows_removed, docs)

    write_documents(database, docs)
    after = db_stats(database)
    stored = database.command("collStats", COLLECTION)
    entries = sum(d["n_entries"] for d in docs)
    print(f"\ndbStats (MB), before -> after: data {before['dataSize']:.1f} -> {after['dataSize']:.1f}, storage {before['storageSize']:.1f} -> "
          f"{after['storageSize']:.1f}, indexes {before['indexSize']:.1f} -> {after['indexSize']:.1f}, total {before['totalSize']:.1f} -> {after['totalSize']:.1f}")
    print(f"{COLLECTION}: {stored['count']:,} documents, {entries:,} entries; BSON size {stored['size'] / 1e6:.1f} MB = {stored['size'] / entries:.0f} bytes per entry "
          f"(estimate was ~95), on disk (compressed) {stored['storageSize'] / 1e6:.1f} MB")
    nirav = nirav_line(database)
    REPORT.write_text(ki.funnel_markdown(len(sample), sample["user_id"].nunique(), funnel, users_removed, rows_removed, docs, nirav),
                      encoding="utf-8", newline="\n")
    print(f"Wrote {REPORT.relative_to(PROJECT_ROOT)}. (0 AniList requests used.)")
    if after["totalSize"] > STOP_MB:
        raise config.ConfigError(f"the database is {after['totalSize']:.0f} MB, over {STOP_MB} MB: stop and report (spec section 5 fallback list)")


if __name__ == "__main__":
    try:
        main()
    except config.ConfigError as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nStopped: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
