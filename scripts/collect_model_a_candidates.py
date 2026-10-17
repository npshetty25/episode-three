"""List the anime Model A can use (Fall 2018 -> Summer 2026) into model_a_candidates.

Run from the episode-three folder:
    python -m scripts.collect_model_a_candidates --dry-run   # no network: shows the plan
    python -m scripts.collect_model_a_candidates             # collect (resumable)
    python -m scripts.collect_model_a_candidates --force     # collect every season again
    python -m scripts.collect_model_a_candidates --test      # use the episode_three_test database

Seasons already collected are skipped with 0 requests, so a crash only costs the
season that was in progress.
"""
import argparse
import sys
from pathlib import Path

# Lets "python scripts\collect_model_a_candidates.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from episode_three import anilist_sync, config, db
from episode_three.clients import anilist
from episode_three.collect import model_a_candidates as candidates

TEST_DB = "episode_three_test"
PROBE_REQUEST_CAP = 15
TASK_REQUEST_CAP = 120


def dry_run():
    seasons = list(candidates.season_range())
    print(f"{len(seasons)} seasons, {seasons[0][0]} {seasons[0][1]} ... {seasons[-1][0]} {seasons[-1][1]}:")
    for start in range(0, len(seasons), 4):
        print("  " + ", ".join(f"{s} {y}" for s, y in seasons[start:start + 4]))
    print(f"\nRequest budget: listing <= {candidates.LISTING_REQUEST_CAP}, airing probe <= {PROBE_REQUEST_CAP}, "
          f"hard cap for the task {TASK_REQUEST_CAP}.")
    print("Dry run: 0 requests (no network, no database).")


def print_summary(database):
    per_season, reasons = candidates.summary_from_db(database)
    print("\nStored candidates per season:")
    total_listed = total_eligible = 0
    for season, year in candidates.season_range():
        listed, eligible = per_season.get((season, year), (0, 0))
        total_listed, total_eligible = total_listed + listed, total_eligible + eligible
        print(f"  {season:<7} {year}  listed {listed:>3}  eligible {eligible:>3}")
    share = total_eligible / total_listed if total_listed else 0
    print(f"  TOTAL           listed {total_listed:>4}  eligible {total_eligible:>4} ({share:.0%})")
    print("\nExclusion reasons (a show can have several):")
    for code, count in sorted(reasons.items(), key=lambda item: -item[1]):
        print(f"  {code:<22} {count:>4}  ({count / total_listed:.0%} of listed)" if total_listed else f"  {code}")


def main():
    parser = argparse.ArgumentParser(description="Collect the Model A candidate list from AniList.")
    parser.add_argument("--dry-run", action="store_true", help="show the plan; no network, no database")
    parser.add_argument("--force", action="store_true", help="collect every season again")
    parser.add_argument("--test", action="store_true", help=f"use the {TEST_DB} database")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")

    if args.dry_run:
        dry_run()
        return

    database = db.get_client()[TEST_DB if args.test else config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)  # fail fast: before any AniList request

    all_seasons = list(candidates.season_range())
    done = set() if args.force else candidates.completed_seasons(database)
    todo = [season for season in all_seasons if season not in done]
    if not todo:
        print(f"{len(all_seasons)}/{len(all_seasons)} seasons already collected, 0 requests")
        print_summary(database)
        return
    print(f"{len(all_seasons) - len(todo)}/{len(all_seasons)} seasons already collected; "
          f"collecting {len(todo)} (cap {candidates.LISTING_REQUEST_CAP} requests)\n")

    candidates.create_indexes(database)
    requests_at_start = anilist.stats["requests"]
    stopped = None
    for season, year in todo:
        try:
            result = candidates.collect_season(database, season, year, requests_at_start)
        except candidates.RequestBudgetExceeded as error:
            stopped = str(error)
            break
        note = "" if result["per_page"] == 50 else f"  (page size {result['per_page']}: complexity fallback)"
        print(f"{season:<7} {year}  listed {result['listed']:>3}  eligible {result['eligible']:>3}  "
              f"requests {result['requests']}{note}", flush=True)

    used = anilist.stats["requests"] - requests_at_start
    print(f"\nAniList requests used: {used} (cap {candidates.LISTING_REQUEST_CAP}); "
          f"HTTP 429s: {anilist.stats['http_429']}; retries: {anilist.stats['retries']}")
    print_summary(database)
    if stopped:
        print(f"\nSTOPPED: {stopped}. Run again to continue (finished seasons are skipped).")
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
