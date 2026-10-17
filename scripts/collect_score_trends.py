"""Collect the daily score trends for window 1 (premiere -> episode 4) into score_trends.

Run from the episode-three folder:
    python -m scripts.collect_score_trends --window w1 --dry-run          # 0 requests: the plan
    python -m scripts.collect_score_trends --window w1 --limit-batches 5  # the pilot
    python -m scripts.collect_score_trends --window w1                    # the full run (resumable)
    python -m scripts.collect_score_trends --window w1 --force            # collect everything again

Shows that already have a w1 status are skipped, so a re-run costs 0 requests. The request cap
counts every earlier run of this script (read from sync_runs), so the pilot is included.
"""
import argparse
import math
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Lets "python scripts\collect_score_trends.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import UpdateOne

from episode_three import anilist_sync, config, db
from episode_three.clients import anilist
from episode_three.collect import airing_markers as markers
from episode_three.collect import model_a_candidates as candidates
from episode_three.collect import score_trends as trends


def load_todo(database, force):
    query = {"eligible": True, "collection_status": "ready"}
    if not force:
        query["w1_status"] = {"$exists": False}
    return list(database[candidates.COLLECTION].find(query))


def requests_already_used(database):
    """Requests spent by earlier runs of this script (the pilot counts toward the cap)."""
    return sum(run.get("requests_used", 0) for run in database["sync_runs"].find({"job": trends.JOB}))


def pages_for(records):
    return max(1, math.ceil(records / 50))


def print_plan(batches, previous):
    isolated = sum(1 for b in batches if len(b) == 1 and markers.window_days(
        b[0]["trend_windows"]["w1"]) > trends.LONG_WINDOW_DAYS)
    widths = [markers.window_days(trends.union_window(b)) for b in batches]
    dist = markers.length_distribution(widths)
    lower = sum(pages_for(trends.estimate_batch_records(b)[0]) for b in batches)
    upper = sum(pages_for(trends.estimate_batch_records(b)[1]) for b in batches)
    print(f"{sum(len(b) for b in batches)} shows -> {len(batches)} batches "
          f"({len(batches) - isolated} normal, {isolated} long-window shows alone)")
    print(f"Union-window width in days (min / median / p95 / max): "
          f"{dist['min']} / {dist['median']:g} / {dist['p95']} / {dist['max']}")
    print(f"Planned minimum requests (one page per batch): {len(batches)}")
    print(f"Estimated requests from the window lengths: {lower} (own windows) to {upper} (union windows)")
    print(f"Cap: {trends.TASK_REQUEST_CAP} for the whole task; earlier runs used {previous}")


def print_summary(database):
    docs = list(database[candidates.COLLECTION].find(
        {"eligible": True, "collection_status": "ready"}, {"w1_status": 1}))
    status = Counter(d.get("w1_status", "not collected") for d in docs)
    print("\nw1 status of the ready shows: " + ", ".join(f"{k} {v}" for k, v in sorted(status.items())))
    snapshots = [d.get("n_snapshots_w1", 0) for d in database[trends.COLLECTION].find({}, {"n_snapshots_w1": 1})]
    if snapshots:
        dist = markers.length_distribution(snapshots)
        print(f"score_trends: {len(snapshots)} documents, snapshots per show min {dist['min']} / "
              f"median {dist['median']:g} / max {dist['max']}")


def print_w2_projection(database, density):
    docs = list(database[candidates.COLLECTION].find(
        {"eligible": True, "collection_status": "ready"}, {"trend_windows": 1}))
    est = markers.estimate_pages(docs, "w2")
    print(f"\nProjected w2 budget: w2 has no releasing filter, so AniList returns a record for EVERY show-day "
          f"(density 1, not the w1 density of {density:.2f}).")
    print(f"  w2: {est['batches']} batches, {est['records_upper']:,} records on union windows "
          f"-> about {est['pages_upper']} requests (floor {est['pages_lower']} if windows were exact).")


def main():
    parser = argparse.ArgumentParser(description="Collect the daily score trends for a window.")
    parser.add_argument("--window", choices=["w1"], required=True, help="w1 = premiere to episode 4")
    parser.add_argument("--limit-batches", type=int, help="the pilot: stop after this many batches")
    parser.add_argument("--dry-run", action="store_true", help="show the plan; 0 requests")
    parser.add_argument("--force", action="store_true", help="collect shows that already have a w1 status")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")

    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)  # fail fast: before any AniList request

    todo = load_todo(database, args.force)
    previous = requests_already_used(database)
    if not todo:
        print("all shows already collected, 0 requests")
        print_summary(database)
        return
    batches = trends.make_w1_batches(todo)
    if args.limit_batches:
        batches = batches[:args.limit_batches]
    print_plan(batches, previous)
    if args.dry_run:
        print("Dry run: 0 requests.")
        return

    started = datetime.now(timezone.utc)
    run_id = f"{trends.JOB}:{started:%Y-%m-%dT%H:%M:%SZ}"
    began = time.monotonic()
    requests_at_start = anilist.stats["requests"]

    def check_budget():
        if previous + anilist.stats["requests"] - requests_at_start >= trends.TASK_REQUEST_CAP:
            raise candidates.RequestBudgetExceeded(f"the cap of {trends.TASK_REQUEST_CAP} requests would be exceeded")

    actual_total = lower_total = upper_total = duplicates_total = own_days = 0
    done_shows = 0
    stop_reason = None
    pilot = bool(args.limit_batches)
    for number, batch in enumerate(batches, 1):
        requests_before = anilist.stats["requests"]
        try:
            rows = trends.fetch_trends([markers.anilist_id(d) for d in batch], trends.union_window(batch), check_budget)
        except candidates.RequestBudgetExceeded as error:
            stop_reason = str(error)
            break
        by_show, duplicates = trends.parse_trend_rows(rows)
        collected_at = datetime.now(timezone.utc)
        pairs = [(d, trends.build_updates(d, by_show.get(markers.anilist_id(d), []), collected_at)) for d in batch]
        # score_trends first, the candidate's status LAST: a crash in between just redoes the batch.
        database[trends.COLLECTION].bulk_write(
            [UpdateOne({"_id": d["_id"]}, {"$set": fields}, upsert=True) for d, (fields, _) in pairs], ordered=False)
        database[candidates.COLLECTION].bulk_write(
            [UpdateOne({"_id": d["_id"]}, {"$set": cand}) for d, (_, cand) in pairs], ordered=False)

        lower, upper = trends.estimate_batch_records(batch)
        actual_total, lower_total, upper_total = actual_total + len(rows), lower_total + lower, upper_total + upper
        duplicates_total += duplicates
        own_days += lower
        done_shows += len(batch)
        used = anilist.stats["requests"] - requests_at_start
        database["sync_runs"].update_one({"_id": run_id}, {"$set": {
            "job": trends.JOB, "started_at": started, "batches_done": number, "batches_planned": len(batches),
            "shows_done": done_shows, "records": actual_total, "duplicates": duplicates_total,
            "requests_used": used}}, upsert=True)
        if pilot or number % 10 == 0 or number == len(batches):
            print(f"  batch {number}/{len(batches)}: {len(batch)} shows, {len(rows)} records "
                  f"(estimate {lower} to {upper}), {anilist.stats['requests'] - requests_before} requests", flush=True)
        if number == 5 and lower_total and actual_total / lower_total > trends.PILOT_RATIO_LIMIT:
            stop_reason = (f"records per batch are {actual_total / lower_total:.2f}x the estimate "
                           f"(limit {trends.PILOT_RATIO_LIMIT}x) after 5 batches")
            break

    used = anilist.stats["requests"] - requests_at_start
    database["sync_runs"].update_one({"_id": run_id}, {"$set": {
        "job": trends.JOB, "finished_at": datetime.now(timezone.utc), "requests_used": used}}, upsert=True)
    runtime = time.monotonic() - began
    print(f"\nRun: {done_shows} shows in {runtime / 60:.1f} min; AniList requests used: {used} "
          f"(cap {trends.TASK_REQUEST_CAP}, earlier runs {previous}); HTTP 429s: {anilist.stats['http_429']}; "
          f"retries: {anilist.stats['retries']}")
    if lower_total:
        print(f"Records: {actual_total:,} vs estimate {lower_total:,} (own windows) to {upper_total:,} (union windows): "
              f"{actual_total / lower_total:.2f}x the lower estimate; duplicates removed: {duplicates_total}")
    print_summary(database)
    if lower_total:
        print_w2_projection(database, actual_total / own_days if own_days else 0)
    if stop_reason:
        print(f"\nSTOPPED: {stop_reason}. Paste this output to the instructor.")
        sys.exit(3 if "x the estimate" in stop_reason else 2)
    if pilot:
        print("\nPilot finished. If records per batch are within 1.3x the estimate, run the full collection.")


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
