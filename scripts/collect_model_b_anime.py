"""Fetch AniList show features for every anime Model B trains on or scores, into model_b_anime.

Run from the episode-three folder:
    python -m scripts.collect_model_b_anime --dry-run    # the plan: universe sizes, requests; 0 requests
    python -m scripts.collect_model_b_anime              # collect (resumable)
    python -m scripts.collect_model_b_anime --force      # fetch every anime again
    --limit-chunks N   stop after N requests' worth of ids (a small trial)

Universe = the anime in the Kaggle sample (MAL ids, idMal_in) + Nirav's TV completed/dropped entries and his
planning/current entries (idMal_in, or id_in for a title without a MAL id), deduplicated before any request.
A MAL id AniList does not know goes to model_b_unmapped (recorded, never guessed). Ids already stored are skipped, so a
re-run costs 0 requests. Hard cap: 160 requests for the whole task (earlier runs count, read from sync_runs).
"""
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Lets "python scripts\collect_model_b_anime.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from pymongo import ReplaceOne

from episode_three import anilist_sync, config, db
from episode_three.clients import anilist
from episode_three.collect import model_a_candidates as candidates
from episode_three.collect import model_b_anime as mba

SAMPLE_PATH = PROJECT_ROOT / "data" / "processed" / "mal_sample_5k_seed42.parquet"


def load_universe(database):
    sample_ids = pd.read_parquet(SAMPLE_PATH, columns=["anime_id"])["anime_id"].unique()
    titles = {t["_id"]: t for t in database["titles"].find({}, {"mal_id": 1, "anilist_id": 1, "format": 1, "is_adult": 1})}
    entries = list(database["my_entries"].find({"source": "anilist"}, {"title_id": 1, "anilist_status": 1}))
    return mba.build_universe(sample_ids, entries, titles)


def stored_state(database):
    stored = list(database[mba.COLLECTION].find({}, {"mal_id": 1, "anilist_id": 1}))
    unmapped = [d["mal_id"] for d in database[mba.UNMAPPED].find({}, {"mal_id": 1})]
    return [d["mal_id"] for d in stored if d.get("mal_id") is not None], [d["anilist_id"] for d in stored], unmapped


def requests_already_used(database):
    return sum(run.get("requests_used", 0) for run in database["sync_runs"].find({"job": mba.JOB}))


def print_plan(universe, mal_todo, anilist_todo, previous, per_page):
    planned = mba.planned_requests(len(mal_todo), len(anilist_todo), per_page)
    print(f"Universe: {universe['total']:,} anime = Kaggle sample {universe['kaggle']:,} + Nirav {universe['nirav']:,} "
          f"- overlap {universe['overlap']:,}  ({len(universe['mal_ids']):,} by MAL id, {len(universe['anilist_ids']):,} by AniList id)")
    print(f"Still to fetch: {len(mal_todo):,} by MAL id + {len(anilist_todo):,} by AniList id "
          f"(already stored or known unmapped: {universe['total'] - len(mal_todo) - len(anilist_todo):,})")
    print(f"Planned requests: {planned} ({per_page} ids per request); cap {mba.TASK_REQUEST_CAP}; "
          f"earlier runs used {previous}; after this run about {previous + planned}")
    return planned


def write_chunk(database, docs, unmapped):
    if docs:
        database[mba.COLLECTION].bulk_write([ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in docs], ordered=False)
        database[mba.UNMAPPED].delete_many({"mal_id": {"$in": [d["mal_id"] for d in docs if d["mal_id"] is not None]}})
    if unmapped:
        database[mba.UNMAPPED].bulk_write([ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in unmapped], ordered=False)


def print_summary(database):
    mapped = database[mba.COLLECTION].count_documents({})
    unmapped = list(database[mba.UNMAPPED].find({}, {"mal_id": 1}).sort("mal_id", 1))
    usable = database[mba.COLLECTION].count_documents({"drop_share": {"$ne": None}})
    print(f"\nmodel_b_anime: {mapped:,} documents ({usable:,} with a usable drop_share); "
          f"model_b_unmapped: {len(unmapped):,} MAL ids AniList does not know")
    if unmapped:
        print("  examples: " + ", ".join(str(d["mal_id"]) for d in unmapped[:5]))


def main():
    parser = argparse.ArgumentParser(description="Collect the Model B show features from AniList.")
    parser.add_argument("--dry-run", action="store_true", help="show the plan; 0 requests")
    parser.add_argument("--force", action="store_true", help="fetch every anime again")
    parser.add_argument("--limit-chunks", type=int, help="stop after this many chunks (a small trial)")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")

    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)  # fail fast: before any AniList request
    universe = load_universe(database)
    stored_mal, stored_anilist, unmapped_mal = stored_state(database)
    mal_todo, anilist_todo = mba.todo_ids(universe, stored_mal, stored_anilist, unmapped_mal, args.force)
    previous = requests_already_used(database)
    if not mal_todo and not anilist_todo:
        print(f"Universe: {universe['total']:,} anime.")
        print("all anime already stored, 0 requests")
        print_summary(database)
        return
    per_page = mba.PER_PAGE
    planned = print_plan(universe, mal_todo, anilist_todo, previous, per_page)
    if previous + planned > mba.TASK_REQUEST_CAP:
        raise config.ConfigError(f"the plan ({previous + planned} requests) is over the cap of {mba.TASK_REQUEST_CAP}")
    if args.dry_run:
        print("Dry run: 0 requests.")
        return

    database[mba.COLLECTION].create_index("mal_id")
    started = datetime.now(timezone.utc)
    run_id = f"{mba.JOB}:{started:%Y-%m-%dT%H:%M:%SZ}"
    began, requests_at_start = time.monotonic(), anilist.stats["requests"]

    def check_budget():
        if previous + anilist.stats["requests"] - requests_at_start >= mba.TASK_REQUEST_CAP:
            raise candidates.RequestBudgetExceeded(f"the cap of {mba.TASK_REQUEST_CAP} requests would be exceeded")

    mapped_total = unmapped_total = chunks_done = 0
    stopped = None
    for by_mal_id, remaining in ((True, list(mal_todo)), (False, list(anilist_todo))):
        while remaining:
            if args.limit_chunks and chunks_done >= args.limit_chunks:
                stopped = f"stopped after {chunks_done} chunk(s) as asked (--limit-chunks)"
                break
            ids = remaining[:per_page]
            try:
                rows = mba.fetch_chunk(ids, by_mal_id, per_page, check_budget)
            except candidates.RequestBudgetExceeded as error:
                stopped = str(error)
                break
            except anilist.AniListError as error:
                if "complex" in str(error).lower() and per_page == mba.PER_PAGE:
                    per_page = 25     # AniList reports a complexity error: ask for 25 per request from now on
                    print(f"  complexity error at {mba.PER_PAGE} per request: continuing with {per_page} per request", flush=True)
                    continue
                raise
            docs, unmapped = mba.split_answer(ids, rows, by_mal_id)
            write_chunk(database, docs, unmapped)
            del remaining[:len(ids)]
            mapped_total, unmapped_total, chunks_done = mapped_total + len(docs), unmapped_total + len(unmapped), chunks_done + 1
            database["sync_runs"].update_one({"_id": run_id}, {"$set": {
                "job": mba.JOB, "started_at": started, "chunks_done": chunks_done, "per_page": per_page,
                "mapped": mapped_total, "unmapped": unmapped_total,
                "requests_used": anilist.stats["requests"] - requests_at_start}}, upsert=True)
            if chunks_done % 10 == 0:
                print(f"  {chunks_done} chunks: {mapped_total:,} mapped, {unmapped_total:,} unmapped, "
                      f"{anilist.stats['requests'] - requests_at_start} requests", flush=True)
        if stopped:
            break

    used = anilist.stats["requests"] - requests_at_start
    database["sync_runs"].update_one({"_id": run_id}, {"$set": {
        "job": mba.JOB, "finished_at": datetime.now(timezone.utc), "requests_used": used}}, upsert=True)
    print(f"\nRun: {chunks_done} chunks in {(time.monotonic() - began) / 60:.1f} min; this run mapped {mapped_total:,} anime, "
          f"{unmapped_total:,} MAL ids unmapped")
    print(f"AniList requests used: {used} (earlier runs {previous}, total {previous + used} of {mba.TASK_REQUEST_CAP}); "
          f"HTTP 429s: {anilist.stats['http_429']}; retries: {anilist.stats['retries']}")
    print_summary(database)
    if stopped:
        print(f"\nSTOPPED: {stopped}. Run again to continue (stored anime are skipped).")
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except (config.ConfigError, anilist.AniListError) as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        print(f"AniList requests used: {anilist.stats['requests']}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nStopped: " + db.explain_error(error), file=sys.stderr)
        print(f"AniList requests used: {anilist.stats['requests']}", file=sys.stderr)
        sys.exit(1)
