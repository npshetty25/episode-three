"""Find the marker days M(1..4), M(final) and the trend windows for every eligible candidate.

Run from the episode-three folder:
    python -m scripts.collect_airing_markers --dry-run   # 0 AniList requests: the plan only
    python -m scripts.collect_airing_markers             # collect (resumable)
    python -m scripts.collect_airing_markers --force     # redo candidates that already have markers

Candidates that already have markers are skipped, so a re-run costs 0 requests.
(--max-batches N is for developers: it stops after N batches, to test with few requests.)
"""
import argparse
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Lets "python scripts\collect_airing_markers.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import UpdateOne

from episode_three import anilist_sync, config, db
from episode_three.clients import anilist
from episode_three.collect import airing_markers as markers
from episode_three.collect import model_a_candidates as candidates

JOB = "airing_markers"
# The task's hard cap is 200 requests including developer tests, so a run stops at 190.
RUN_REQUEST_CAP = 190


def load_todo(database, force):
    query = {"eligible": True}
    if not force:
        query["markers_fetched_at"] = {"$exists": False}
    return list(database[candidates.COLLECTION].find(query))


def show_plan(batches, total_candidates):
    sizes = Counter(len(group) for n, group in batches)
    print(f"{total_candidates} candidates -> {len(batches)} batches "
          f"({len({n for n, g in batches})} different episode counts)")
    print("Batch sizes: " + ", ".join(f"{size} shows x {count}" for size, count in sorted(sizes.items(), reverse=True)))
    print(f"Planned requests: {len(batches)} (one page per batch; the run stops at {RUN_REQUEST_CAP})")


def fetch_batch(ids, n_episodes, requests_at_start):
    """All schedule rows for one batch (episodes 1-4 and the finale N)."""
    def check_budget():
        if anilist.stats["requests"] - requests_at_start >= RUN_REQUEST_CAP:
            raise candidates.RequestBudgetExceeded(f"the cap of {RUN_REQUEST_CAP} requests would be exceeded")

    episodes = [1, 2, 3, 4, n_episodes]
    return anilist.collect_pages(markers.MARKER_QUERY, {"ids": ids, "eps": episodes},
                                 lambda data: data["Page"]["airingSchedules"], 50, max_pages=4,
                                 before_request=check_budget,
                                 is_complete=lambda rows: markers.covers_every_pair(rows, ids, episodes))


def print_summary(database):
    docs = list(database[candidates.COLLECTION].find(
        {"eligible": True, "markers_fetched_at": {"$exists": True}},
        {"collection_status": 1, "collection_reasons": 1, "marker_source": 1, "markers": 1,
         "season": 1, "season_year": 1, "episodes": 1, "trend_windows": 1}))
    total = len(docs)
    eligible = database[candidates.COLLECTION].count_documents({"eligible": True})
    print(f"\nEligible candidates with markers: {total} of {eligible}")
    status = Counter(d["collection_status"] for d in docs)
    print("Collection status: " + ", ".join(f"{k} {v}" for k, v in sorted(status.items())))
    print("Marker source w1: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(
        str(d["marker_source"]["w1"]) for d in docs).items())))
    print("Marker source w2: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(
        str(d["marker_source"]["w2"]) for d in docs).items())))
    ready_schedule = sum(1 for d in docs if d["collection_status"] == "ready"
                         and d["marker_source"]["w1"] == "schedule")
    print(f"Ready with a schedule-based w1: {ready_schedule} ({ready_schedule / eligible:.0%} of {eligible} eligible)")
    reasons = Counter(r for d in docs for r in d["collection_reasons"])
    if reasons:
        print("Reasons: " + ", ".join(f"{k} {v}" for k, v in sorted(reasons.items())))
    flags = Counter(flag for d in docs for flag, on in d["markers"]["flags"].items() if on)
    print("Flags: " + (", ".join(f"{k} {v}" for k, v in sorted(flags.items())) or "none"))
    pending = Counter(f"{d['season'].title()} {d['season_year']}" for d in docs if d["collection_status"] == "pending")
    if pending:
        print("Pending shows by season: " + ", ".join(f"{k} {v}" for k, v in pending.items()))
    missing_final = [d["_id"] for d in docs if d["markers"]["flags"]["finale_row_missing"]]
    if missing_final:
        print(f"Shows whose schedule has no row for episode N (finale episode != episodes): {len(missing_final)}")
        print("  " + ", ".join(missing_final[:15]) + (" ..." if len(missing_final) > 15 else ""))


def main():
    parser = argparse.ArgumentParser(description="Collect marker days and trend windows from AniList schedules.")
    parser.add_argument("--dry-run", action="store_true", help="show the plan; 0 AniList requests")
    parser.add_argument("--force", action="store_true", help="redo candidates that already have markers")
    parser.add_argument("--max-batches", type=int, help="developer option: stop after this many batches")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")

    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)  # fail fast: before any AniList request

    todo = load_todo(database, args.force)
    if not todo:
        print("all candidates already have markers, 0 requests")
        print_summary(database)
        return
    batches = markers.make_batches(todo)
    if args.max_batches:
        batches = batches[:args.max_batches]
    show_plan(batches, sum(len(group) for n, group in batches))
    if args.dry_run:
        print("Dry run: 0 AniList requests.")
        return

    today_jst = markers.jst_day(time.time())
    started = datetime.now(timezone.utc)
    run_id = f"{JOB}:{started:%Y-%m-%dT%H:%M:%SZ}"
    requests_at_start = anilist.stats["requests"]
    done_shows = 0
    stopped = None
    for number, (n_episodes, group) in enumerate(batches, 1):
        try:
            rows = fetch_batch([markers.anilist_id(d) for d in group], n_episodes, requests_at_start)
        except candidates.RequestBudgetExceeded as error:
            stopped = str(error)
            break
        by_show = markers.group_rows_by_show(rows)
        fetched_at = datetime.now(timezone.utc)
        database[candidates.COLLECTION].bulk_write([
            UpdateOne({"_id": d["_id"]}, {"$set": markers.candidate_update(
                d, by_show.get(markers.anilist_id(d), []), n_episodes, today_jst, fetched_at)})
            for d in group], ordered=False)
        done_shows += len(group)
        database["sync_runs"].update_one({"_id": run_id}, {"$set": {
            "job": JOB, "started_at": started, "batches_done": number, "batches_planned": len(batches),
            "shows_done": done_shows, "requests_used": anilist.stats["requests"] - requests_at_start}}, upsert=True)
        if number % 10 == 0 or number == len(batches):
            print(f"  batch {number}/{len(batches)}: {done_shows} shows, "
                  f"{anilist.stats['requests'] - requests_at_start} requests", flush=True)

    used = anilist.stats["requests"] - requests_at_start
    database["sync_runs"].update_one({"_id": run_id}, {"$set": {
        "job": JOB, "finished_at": datetime.now(timezone.utc), "requests_used": used}}, upsert=True)
    print(f"\nAniList requests used: {used} (cap {RUN_REQUEST_CAP}); HTTP 429s: {anilist.stats['http_429']}; "
          f"retries: {anilist.stats['retries']}")
    print_summary(database)
    if stopped:
        print(f"\nSTOPPED: {stopped}. Run again to continue (candidates with markers are skipped).")
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
