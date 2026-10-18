"""Collect the daily score trends for window 1 (premiere -> episode 4) or window 2 (finale -> finale + 10).

Run from the episode-three folder:
    python -m scripts.collect_score_trends --window w1 --dry-run   # 0 requests: the plan
    python -m scripts.collect_score_trends --window w1             # window 1 (resumable)
    python -m scripts.collect_score_trends --window w2 --dry-run   # also compares the union-width caps
    python -m scripts.collect_score_trends --window w2             # window 2 (the LABEL data)
    --limit-batches N  stop after N batches (a small trial);  --force  collect shows that already have a status

Shows that already have a status for the window are skipped, so a re-run costs 0 requests. The request cap
counts every earlier run of the same window (read from sync_runs).

Stop rule: after every batch the script compares the records AniList really returned with what the model
predicted; after enough batches it stops if actual / predicted is above 1.15 (10 batches for w1, 5 for w2).

w2 data is LABEL data. It is stored in snapshots_w2 and feature code must never read it.
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

WINDOWS = {
    "w1": {"job": trends.JOB, "query": trends.TREND_QUERY, "make_batches": trends.make_w1_batches,
           "predict": trends.predict_batch_records, "min_batches": trends.STOP_MIN_BATCHES,
           "cap": trends.TASK_REQUEST_CAP, "reserve": 0},
    "w2": {"job": "score_trends_w2", "query": trends.TREND_QUERY_W2, "make_batches": trends.make_w2_batches,
           "predict": trends.predict_w2_batch_records, "min_batches": trends.W2_STOP_MIN_BATCHES,
           "cap": trends.W2_TASK_REQUEST_CAP, "reserve": trends.W2_PROBE_RESERVE},
}


def load_ready(database):
    return list(database[candidates.COLLECTION].find({"eligible": True, "collection_status": "ready"}))


def requests_already_used(database, job):
    """Requests spent by earlier runs of this window (they count toward the cap)."""
    return sum(run.get("requests_used", 0) for run in database["sync_runs"].find({"job": job}))


def print_plan(window, batches, previous, cfg):
    widths = markers.length_distribution(
        [markers.window_days(trends.union_window(b, window)) for b in batches])
    predicted = [cfg["predict"](b) for b in batches]
    requests_needed = sum(trends.predicted_requests(r) for r in predicted)
    print(f"{sum(len(b) for b in batches)} shows to collect -> {len(batches)} batches")
    print(f"Union-window width in days (min / median / p95 / max): "
          f"{widths['min']} / {widths['median']:g} / {widths['p95']} / {widths['max']}")
    print(f"Predicted records: {sum(predicted):,}")
    print(f"Predicted requests: {requests_needed} (at least {len(batches)}, one page per batch)")
    print(f"Cap: {cfg['cap']} for the whole task (minus {cfg['reserve']} reserved); earlier runs of {window} "
          f"used {previous}; after this run about {previous + requests_needed}")


def print_cap_comparison(docs):
    rows = trends.w2_cap_comparison(docs)
    best = trends.choose_w2_cap(rows)
    print("\nw2 union-width cap comparison (predicted; one record per show-day, requests = records // 50 + 1):")
    print("  cap (days) | batches | predicted records | predicted requests")
    for row in rows:
        mark = "  <- cheapest" if row["cap"] == best else ""
        print(f"  {row['cap']:>10} | {row['batches']:>7} | {row['records']:>17,} | {row['requests']:>18}{mark}")
    print(f"Chosen (fewest predicted requests): {best} days. In the code: W2_MAX_UNION_DAYS = {trends.W2_MAX_UNION_DAYS}"
          + ("" if best == trends.W2_MAX_UNION_DAYS else "  <-- DIFFERENT: set the constant to the chosen cap"))


def print_summary(database, window):
    field = f"{window}_status"
    docs = list(database[candidates.COLLECTION].find(
        {"eligible": True, "collection_status": "ready"}, {field: 1, "format": 1, "episodes": 1}))
    status = Counter(d.get(field, "not collected") for d in docs)
    print(f"\n{field} of the ready shows: " + ", ".join(f"{k} {v}" for k, v in sorted(status.items())))
    empty = [d for d in docs if d.get(field) == "no_records"]
    if empty:
        print("no_records shows: " + ", ".join(f"{d['_id']} ({d['format']}, {d['episodes']} eps)" for d in empty))
    counts = [d.get(f"n_snapshots_{window}", 0) for d in database[trends.COLLECTION].find(
        {f"n_snapshots_{window}": {"$exists": True}}, {f"n_snapshots_{window}": 1})]
    if counts:
        dist = markers.length_distribution(counts)
        print(f"score_trends: {len(counts)} documents with {window} snapshots, per show min {dist['min']} / "
              f"median {dist['median']:g} / max {dist['max']}")


def main():
    parser = argparse.ArgumentParser(description="Collect the daily score trends for a window.")
    parser.add_argument("--window", choices=["w1", "w2"], required=True, help="w1 = premiere..ep4, w2 = finale")
    parser.add_argument("--limit-batches", type=int, help="stop after this many batches (a small trial)")
    parser.add_argument("--dry-run", action="store_true", help="show the plan; 0 requests")
    parser.add_argument("--force", action="store_true", help="collect shows that already have a status")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")
    window, cfg = args.window, WINDOWS[args.window]
    status_field = f"{window}_status"

    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)  # fail fast: before any AniList request

    ready = load_ready(database)
    todo = [d for d in ready if args.force or status_field not in d]
    previous = requests_already_used(database, cfg["job"])
    skipped_ids = []
    if window == "w2":
        # a show without w1 has no features, so its label would be useless: no w2 request for it
        skipped_ids = [d["_id"] for d in todo if d.get("w1_status") != "collected"]
        todo = [d for d in todo if d.get("w1_status") == "collected"]
    if not todo and not skipped_ids:
        print("all shows already collected, 0 requests")
        print_summary(database, window)
        return
    batches = cfg["make_batches"](todo)
    if args.limit_batches:
        batches = batches[:args.limit_batches]
    if window == "w2":
        print(f"{len(skipped_ids)} shows have no w1 data and are marked skipped_no_w1 (no request).")
        print_cap_comparison(todo)
    if batches:
        print_plan(window, batches, previous, cfg)
    if args.dry_run:
        print("Dry run: 0 requests.")
        return
    if skipped_ids:
        database[candidates.COLLECTION].update_many({"_id": {"$in": skipped_ids}}, {"$set": {status_field: "skipped_no_w1"}})

    database[trends.COLLECTION].create_index([("season_year", 1), ("season", 1)])  # does nothing if it exists
    started = datetime.now(timezone.utc)
    run_id = f"{cfg['job']}:{started:%Y-%m-%dT%H:%M:%SZ}"
    began = time.monotonic()
    requests_at_start = anilist.stats["requests"]

    def check_budget():
        if previous + anilist.stats["requests"] - requests_at_start >= cfg["cap"] - cfg["reserve"]:
            raise candidates.RequestBudgetExceeded(f"the cap of {cfg['cap']} requests would be exceeded")

    actual_total = predicted_total = duplicates_total = done_shows = 0
    stop_reason = None
    for number, batch in enumerate(batches, 1):
        requests_before = anilist.stats["requests"]
        try:
            rows = trends.fetch_trends([markers.anilist_id(d) for d in batch], trends.union_window(batch, window),
                                       check_budget, query=cfg["query"])
        except candidates.RequestBudgetExceeded as error:
            stop_reason = str(error)
            break
        by_show, duplicates = trends.parse_trend_rows(rows)
        collected_at = datetime.now(timezone.utc)
        pairs = [(d, trends.build_updates(d, by_show.get(markers.anilist_id(d), []), collected_at, window))
                 for d in batch]
        # score_trends first, the candidate's status LAST: a crash in between just redoes the batch.
        database[trends.COLLECTION].bulk_write(
            [UpdateOne({"_id": d["_id"]}, {"$set": fields}, upsert=True) for d, (fields, _) in pairs], ordered=False)
        database[candidates.COLLECTION].bulk_write(
            [UpdateOne({"_id": d["_id"]}, {"$set": cand}) for d, (_, cand) in pairs], ordered=False)

        predicted = cfg["predict"](batch)
        actual_total, predicted_total = actual_total + len(rows), predicted_total + predicted
        duplicates_total += duplicates
        done_shows += len(batch)
        stop, ratio = trends.should_stop(actual_total, predicted_total, number, cfg["min_batches"])
        database["sync_runs"].update_one({"_id": run_id}, {"$set": {
            "job": cfg["job"], "started_at": started, "batches_done": number, "batches_planned": len(batches),
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
        "job": cfg["job"], "finished_at": datetime.now(timezone.utc), "requests_used": used}}, upsert=True)
    print(f"\nRun: {done_shows} shows in {(time.monotonic() - began) / 60:.1f} min; AniList requests used: {used} "
          f"(earlier runs of {window} {previous}, total {previous + used} of {cfg['cap']}); "
          f"HTTP 429s: {anilist.stats['http_429']}; retries: {anilist.stats['retries']}")
    if predicted_total:
        print(f"Records: actual {actual_total:,} vs predicted {predicted_total:,} "
              f"(ratio {actual_total / predicted_total:.3f}); duplicates removed: {duplicates_total}")
    print_summary(database, window)
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
