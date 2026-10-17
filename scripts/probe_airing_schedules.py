"""Probe: are AniList's PAST airing schedules complete? (TASK 007)

Run from the episode-three folder:
    python -m scripts.probe_airing_schedules          # uses the candidates already in the database
    python -m scripts.probe_airing_schedules --test   # use the episode_three_test database

Picks 10 eligible candidates (evenly spaced by popularity) from each of Fall 2018,
Winter 2022 and Summer 2026 (0 requests), then asks AniList for their schedules in
batches. Raw answers go to data/probes/ (git-ignored). Needs the candidates to be
collected first: python -m scripts.collect_model_a_candidates
"""
import argparse
import json
import sys
from pathlib import Path

# Lets "python scripts\probe_airing_schedules.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from episode_three import anilist_sync, config, db
from episode_three.clients import anilist
from episode_three.collect import airing_probe as probe
from episode_three.collect import model_a_candidates as candidates

TEST_DB = "episode_three_test"
PROBE_SEASONS = [("FALL", 2018), ("WINTER", 2022), ("SUMMER", 2026)]
SHOWS_PER_SEASON = 10
REQUEST_CAP = 15
MAX_PAGES = 8
RAW_DIR = PROJECT_ROOT / "data" / "probes"
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "airing_schedules_sample.json"


def fetch_schedules(ids, requests_at_start):
    """All schedule rows for a batch of shows (pages until hasNextPage is false)."""
    rows, pages = [], []
    for page in range(1, MAX_PAGES + 1):
        if anilist.stats["requests"] - requests_at_start >= REQUEST_CAP:
            raise candidates.RequestBudgetExceeded(f"the probe cap of {REQUEST_CAP} requests would be exceeded")
        data = anilist.post_query(probe.AIRING_QUERY, {"ids": ids, "page": page})
        pages.append(data)
        rows.extend(data["Page"]["airingSchedules"])
        if not data["Page"]["pageInfo"]["hasNextPage"]:
            return rows, pages
    raise anilist.AniListError(f"more than {MAX_PAGES} pages for one batch; stopping as a safety measure")


def save_fixture_once(shows, rows_by_show):
    """Save one trimmed response (one complete show) as a test fixture, but never overwrite it."""
    if FIXTURE_PATH.exists():
        return False
    for doc in shows:
        rows = rows_by_show.get(probe.anilist_id(doc), [])
        if rows and probe.summarize_show_schedule(rows, doc["episodes"])["status"] == "complete":
            FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
            trimmed = {"_note": f"One show's real airingSchedules rows, trimmed from the TASK 007 probe. "
                                f"The show has {doc['episodes']} episodes.",
                       "episodes": doc["episodes"],
                       "data": {"Page": {"pageInfo": {"hasNextPage": False}, "airingSchedules": rows}}}
            FIXTURE_PATH.write_text(json.dumps(trimmed, indent=1) + "\n", encoding="utf-8")
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Probe AniList's past airing schedules.")
    parser.add_argument("--test", action="store_true", help=f"use the {TEST_DB} database")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")

    database = db.get_client()[TEST_DB if args.test else config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)  # fail fast: before any AniList request
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    requests_at_start = anilist.stats["requests"]
    verdicts, fixture_saved = [], False
    for season, year in PROBE_SEASONS:
        docs = list(database[candidates.COLLECTION].find({"season": season, "season_year": year}))
        shows = probe.pick_probe_shows(docs, SHOWS_PER_SEASON)
        print(f"\n=== {season} {year}: {len(docs)} candidates, {sum(1 for d in docs if d['eligible'])} eligible, "
              f"probing {len(shows)}")
        if not shows:
            print("  no eligible candidates stored; run python -m scripts.collect_model_a_candidates first")
            verdicts.append((season, year, "no candidates", "none"))
            continue

        rows, pages = fetch_schedules([probe.anilist_id(doc) for doc in shows], requests_at_start)
        (RAW_DIR / f"airing_schedules_{season}_{year}.json").write_text(
            json.dumps({"season": season, "year": year, "pages": pages}, indent=1), encoding="utf-8")
        rows_by_show = probe.group_rows_by_show(rows)

        print(f"  {'AniList id':<10} {'eps':>3} {'rows':>4} {'1-4':>4} {'final':>5} {'status':<9} "
              f"{'first airing (JST)':<18} {'last airing (JST)':<18}")
        summaries = []
        for doc in shows:
            summary = probe.summarize_show_schedule(rows_by_show.get(probe.anilist_id(doc), []), doc["episodes"])
            summaries.append(summary)
            print(f"  {probe.anilist_id(doc):<10} {doc['episodes']:>3} {summary['rows']:>4} "
                  f"{'yes' if summary['has_eps_1_to_4'] else 'NO':>4} "
                  f"{'yes' if summary['has_final_episode'] else 'NO':>5} {summary['status']:<9} "
                  f"{summary['first_airing_jst'] or '-':<18} {summary['last_airing_jst'] or '-':<18}")
        detail, verdict = probe.season_verdict(summaries)
        verdicts.append((season, year, detail, verdict))
        if not fixture_saved:
            fixture_saved = save_fixture_once(shows, rows_by_show)

    print("\nVerdict per season:")
    for season, year, detail, verdict in verdicts:
        print(f"  {season} {year}: {verdict.upper()} ({detail})")
    print(f"\nAniList requests used: {anilist.stats['requests'] - requests_at_start} (cap {REQUEST_CAP}); "
          f"HTTP 429s: {anilist.stats['http_429']}")
    if fixture_saved:
        print(f"Saved fixture: {FIXTURE_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except candidates.RequestBudgetExceeded as error:
        print(f"\nSTOPPED: {error}", file=sys.stderr)
        sys.exit(2)
    except (config.ConfigError, anilist.AniListError) as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        print(f"AniList requests used: {anilist.stats['requests']}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nStopped: " + db.explain_error(error), file=sys.stderr)
        print(f"AniList requests used: {anilist.stats['requests']}", file=sys.stderr)
        sys.exit(1)
