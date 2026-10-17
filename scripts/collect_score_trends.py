"""Collect the daily score trends for window 1 (premiere -> episode 4) into score_trends.

Run from the episode-three folder:
    python -m scripts.collect_score_trends --window w1 --dry-run          # 0 requests: the plan
    python -m scripts.collect_score_trends --window w1                    # the collection (resumable)
    python -m scripts.collect_score_trends --window w1 --limit-batches 5  # a small trial
    python -m scripts.collect_score_trends --window w1 --force            # collect everything again

Shows that already have a w1 status are skipped, so a re-run costs 0 requests. The request cap
counts every earlier run of this script (read from sync_runs).

Stop rule: after every batch the script compares the records AniList really returned with what the
airing-overlap model predicted; after 10 batches it stops if actual / predicted is above 1.15.
"""
import argparse
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
    """Requests spent by earlier runs of this script (they count toward the cap)."""
    return sum(run.get("requests_used", 0) for run in database["sync_runs"].find({"job": trends.JOB}))


def print_plan(batches, previous):
    long_alone = sum(1 for b in batches if len(b) == 1 and markers.window_days(
        b[0]["trend_windows"]["w1"]) > trends.W1_MAX_UNION_DAYS)
    widths = markers.length_distribution([markers.window_days(trends.union_window(b)) for b in batches])
    predicted = [trends.predict_batch_records(b) for b in batches]
    requests_needed = sum(trends.predicted_requests(r) for r in predicted)
    print(f"{sum(len(b) for b in batches)} shows to collect -> {len(batches)} batches "
          f"({len(batches) - long_alone} normal, {long_alone} long-window shows alone)")
    print(f"Union-window width in days (min / median / p95 / max): "
          f"{widths['min']} / {widths['median']:g} / {widths['p95']} / {widths['max']} "
          f"(cap {trends.W1_MAX_UNION_DAYS} days per batch)")
    print(f"Predicted records: {sum(predicted):,}")
    print(f"Predicted requests: {requests_needed} (at least {len(batches)}, one page per batch)")
    print(f"Cap: {trends.TASK_REQUEST_CAP} for the whole task; earlier runs used {previous}; "
          f"after this run about {previous + requests_needed}")


def print_summary(database):
    docs = list(database[candidates.COLLECTION].find(
        {"eligible": True, "collection_status": "ready"}, {"w1_status": 1, "format": 1, "episodes": 1}))
    status = Counter(d.get("w1_status", "not collected") for d in docs)
    print("\nw1 status of the ready shows: " + ", ".join(f"{k} {v}" for k, v in sorted(status.items())))
    empty = [d for d in docs if d.get("w1_status") == "no_records"]
    if empty:
        print("no_records shows: " + ", ".join(f"{d['_id']} ({d['format']}, {d['episodes']} eps)" for d in empty))
    snapshots = [d.get("n_snapshots_w1", 0) for d in database[trends.COLLECTION].find({}, {"n_snapshots_w1": 1})]
    if snapshots:
        dist = markers.length_distribution(snapshots)
        print(f"score_trends: {len(snapshots)} documents, snapshots per show min {dist['min']} / "
              f"median {dist['median']:g} / max {dist['max']}")


def print_w2_projection(database):
    docs = list(database[candidates.COLLECTION].find(
        {"eligible": True, "collection_status": "ready"}, {"trend_windows": 1}))
    batches, records, requests_needed = trends.project_w2(docs)
    print(f"\nProjected w2 (batched by finale date, no releasing filter, so one record per show-day of the "
          f"union window): {batches} batches, {records:,} records, about {requests_needed} requests.")


def main():
    parser = argparse.ArgumentParser(description="Collect the daily score trends for a window.")
    parser.add_argument("--window", choices=["w1"], required=True, help="w1 = premiere to episode 4")
    parser.add_argument("--limit-batches", type=int, help="stop after this many batches (a small trial)")
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
        print_w2_projection(database)
        print("Dry run: 0 requests.")
        return

    database[trends.COLLECTION].create_index([("season_year", 1), ("season", 1)])  # does nothing if it exists
    started = datetime.now(timezone.utc)
    run_id = f"{trends.JOB}:{started:%Y-%m-%dT%H:%M:%SZ}"
    began = time.monotonic()
    requests_at_start = anilist.stats["requests"]

    def check_budget():
        if previous + anilist.stats["requests"] - requests_at_start >= trends.TASK_REQUEST_CAP:
            raise candidates.RequestBudgetExceeded(f"the cap of {trends.TASK_REQUEST_CAP} requests would be exceeded")

    actual_total = predicted_total = duplicates_total = done_shows = 0
    stop_reason = None
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

        predicted = trends.predict_batch_records(batch)
        actual_total, predicted_total = actual_total + len(rows), predicted_total + predicted
        duplicates_total += duplicates
        done_shows += len(batch)
        stop, ratio = trends.should_stop(actual_total, predicted_total, number)
        database["sync_runs"].update_one({"_id": run_id}, {"$set": {
            "job": trends.JOB, "started_at": started, "batches_done": number, "batches_planned": len(batches),
            "shows_done": done_shows, "records": actual_total, "predicted_records": predicted_total,
            "duplicates": duplicates_total, "requests_used": anilist.stats["requests"] - requests_at_start}},
            upsert=True)
        if number % 10 == 0 or number == len(batches) or args.limit_batches:
            print(f"  batch {number}/{len(batches)}: {len(batch)} shows, {len(rows)} records (predicted {predicted}), "
                  f"{anilist.stats['requests'] - requests_before} requests; cumulative actual/predicted "
                  f"{actual_total:,}/{predicted_total:,} = {ratio:.2f}", flush=True)
        if stop:
            stop_reason = (f"actual records are {ratio:.2f}x the model's prediction after {number} batches "
                           f"(limit {trends.STOP_RATIO_LIMIT}x)")
            break

    used = anilist.stats["requests"] - requests_at_start
    database["sync_runs"].update_one({"_id": run_id}, {"$set": {
        "job": trends.JOB, "finished_at": datetime.now(timezone.utc), "requests_used": used}}, upsert=True)
    print(f"\nRun: {done_shows} shows in {(time.monotonic() - began) / 60:.1f} min; AniList requests used: {used} "
          f"(earlier runs {previous}, total {previous + used} of {trends.TASK_REQUEST_CAP}); "
          f"HTTP 429s: {anilist.stats['http_429']}; retries: {anilist.stats['retries']}")
    if predicted_total:
        print(f"Records: actual {actual_total:,} vs predicted {predicted_total:,} "
              f"(ratio {actual_total / predicted_total:.3f}); duplicates removed: {duplicates_total}")
    print_summary(database)
    print_w2_projection(database)
    if stop_reason:
        print(f"\nSTOPPED: {stop_reason}. Run again to continue (finished batches are skipped); "
              "paste this output to the instructor.")
        sys.exit(3 if "x the model" in stop_reason else 2)


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
