"""Sync Nirav's public AniList anime list into MongoDB (read-only; never writes to AniList).

Run from the episode-three folder:
    python scripts\\sync_anilist.py              # into the episode_three database (skipped if synced < 24 h ago)
    python scripts\\sync_anilist.py --force      # sync even if the last sync was recent
    python scripts\\sync_anilist.py --test       # into episode_three_test instead
    python scripts\\sync_anilist.py --stale      # list entries to fix on AniList (no AniList request)
    python scripts\\sync_anilist.py --username someone
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Lets "python scripts\sync_anilist.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from episode_three import anilist_sync, config, db
from episode_three.clients import anilist

TEST_DB = "episode_three_test"


def print_stale(database, username):
    entries = list(database["my_entries"].find(anilist_sync.stored_entries_filter(username)))
    titles = {t["_id"]: t for t in database["titles"].find({"_id": {"$in": [e["title_id"] for e in entries]}})}
    stale = anilist_sync.stale_entries(entries, titles, datetime.now(timezone.utc))
    print(f"\nWatching/Paused entries to check on AniList ({len(stale)}): imported from MAL and not edited "
          f"since, or not updated in {anilist_sync.STALE_AFTER_DAYS} days")
    for row in stale:
        episodes = row["episodes"] if row["episodes"] is not None else "?"
        print(f"  {row['status']:<8} {row['progress']:>5}/{episodes:<5} {row['title'][:55]}  ({row['reason']})")
    print(f"Entries with no start or finish date: {anilist_sync.count_without_dates(entries)} of {len(entries)}")


def main():
    parser = argparse.ArgumentParser(description="Sync a public AniList anime list into MongoDB.")
    parser.add_argument("--username", help="AniList username (default: ANILIST_USERNAME from .env)")
    parser.add_argument("--test", action="store_true", help=f"write to the {TEST_DB} database")
    parser.add_argument("--stale", action="store_true", help="only print the stale-entry report from the database")
    parser.add_argument("--force", action="store_true",
                        help=f"sync even if the last sync was under {anilist_sync.SYNC_MIN_INTERVAL_HOURS} hours ago")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")

    username = args.username or config.get_anilist_username()
    database = db.get_client()[TEST_DB if args.test else config.MONGODB_DB]
    print(f"Database: {database.name} | AniList user: {username}")

    if args.stale:
        print_stale(database, username)
        return

    # Fail fast: check Atlas before any AniList request (a sync is 26 requests).
    anilist_sync.ping_database(database)

    if not args.force:
        last = anilist_sync.last_sync_finished_at(database, username)
        skip, hours = anilist_sync.should_skip_sync(last, datetime.now(timezone.utc))
        if skip:
            print(f"synced {hours:.1f} h ago, use --force "
                  f"(syncs under {anilist_sync.SYNC_MIN_INTERVAL_HOURS} h apart are skipped)")
            print("AniList requests used: 0")
            return

    counts = anilist_sync.sync(database, username)
    # create_index does nothing if the index already exists.
    database["my_entries"].create_index("title_id")
    database["my_entries"].create_index("mal_status_code")

    print(f"\nEntries: fetched {counts['fetched']}, inserted {counts['inserted']}, modified {counts['modified']}, "
          f"unchanged {counts['unchanged']}, deleted {counts['deleted']}")
    t = counts["titles"]
    print(f"Titles:  fetched {t['fetched']}, inserted {t['inserted']}, modified {t['modified']}, "
          f"unchanged {t['unchanged']}  (title scores/popularity change on AniList daily)")
    print("\nBy status:")
    for status, count in counts["by_status"].items():
        print(f"  {status:<10} {count:>4}")
    print(f"  {'TOTAL':<10} {counts['fetched']:>4}")
    print("\nBy origin (burst detection):")
    for origin, count in counts["by_origin"].items():
        print(f"  {origin:<10} {count:>4}")
    print(f"\nAniList requests used: {counts['requests_used']} (HTTP attempts incl. retries)")
    print("Run with --stale to list Watching/Paused entries worth updating on AniList.")


if __name__ == "__main__":
    try:
        main()
    except (config.ConfigError, anilist.AniListError) as error:
        print(f"\nSync stopped: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nSync stopped: " + db.explain_error(error), file=sys.stderr)
        print(f"AniList requests used: {anilist.stats['requests']}", file=sys.stderr)
        sys.exit(1)
