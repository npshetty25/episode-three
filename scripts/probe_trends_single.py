"""Look at one show's raw trend records with ONE request: mediaId only, sorted by DATE.

Run from the episode-three folder:
    python -m scripts.probe_trends_single --media-id 130402

No window, no releasing filter: this shows whether AniList has ANY trend records for the show, and
what they look like. One request returns at most the first 50 records (the earliest by date).
"""
import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Lets "python scripts\probe_trends_single.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from episode_three import config
from episode_three.clients import anilist

JST = timezone(timedelta(hours=9))

QUERY = """
query ($id: Int, $page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    mediaTrends(mediaId: $id, sort: [DATE]) { mediaId date episode averageScore popularity releasing }
  }
}"""


def describe(rows, has_next):
    """A short, printable summary of the first page of trend rows (pure, tested)."""
    if not rows:
        return ["No trend records at all for this show."]
    day = lambda unix: datetime.fromtimestamp(unix, tz=JST).strftime("%Y-%m-%d")
    releasing = Counter(bool(r["releasing"]) for r in rows)
    scored = sum(1 for r in rows if (r["averageScore"] or 0) > 0)
    episodes = sorted({r["episode"] for r in rows if r["episode"] is not None})
    return [
        f"Records on the first page: {len(rows)} (more pages exist: {has_next})",
        f"First date (JST): {day(rows[0]['date'])}; last date on this page: {day(rows[-1]['date'])}",
        f"releasing true: {releasing[True]}, false: {releasing[False]}; scored records: {scored}",
        f"Episode numbers seen: {episodes or 'none'}",
    ]


def main():
    parser = argparse.ArgumentParser(description="Look at one show's raw trend records (1 request).")
    parser.add_argument("--media-id", type=int, required=True, help="the AniList id, e.g. 130402")
    args = parser.parse_args()
    data = anilist.post_query(QUERY, {"id": args.media_id, "page": 1})
    rows = data["Page"]["mediaTrends"]
    print(f"Show {args.media_id}:")
    for line in describe(rows, data["Page"]["pageInfo"]["hasNextPage"]):
        print("  " + line)
    print(f"AniList requests used: {anilist.stats['requests']}")


if __name__ == "__main__":
    try:
        main()
    except (config.ConfigError, anilist.AniListError) as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        print(f"AniList requests used: {anilist.stats['requests']}", file=sys.stderr)
        sys.exit(1)
