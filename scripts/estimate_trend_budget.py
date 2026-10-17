"""Estimate how many AniList requests TASK 009 (trend collection) will need. 0 requests.

Run from the episode-three folder:
    python -m scripts.estimate_trend_budget

Reads the trend windows stored by collect_airing_markers. For each window type (w1 = episodes
1-4, w2 = the finale) shows are sorted by the start of their window and grouped 10 per query.
Each query asks for the UNION of its shows' windows, so:
- upper bound: every show has one trend record per day of the union window;
- lower bound: every show has one record per day of its own window;
pages = ceil(records / 50) per batch. The real number lies in between.
"""
import sys
from collections import Counter
from pathlib import Path

# Lets "python scripts\estimate_trend_budget.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from episode_three import anilist_sync, config, db
from episode_three.collect import airing_markers as markers
from episode_three.collect import model_a_candidates as candidates


def print_estimate(label, docs):
    print(f"\n{label}: {len(docs)} shows")
    totals = {"upper": 0, "lower": 0}
    for key, name in (("w1", "w1 (episodes 1-4)"), ("w2", "w2 (finale)")):
        usable = [d for d in docs if d["trend_windows"][key] is not None]
        est = markers.estimate_pages(usable, key)
        totals["upper"] += est["pages_upper"]
        totals["lower"] += est["pages_lower"]
        print(f"  {name:<18} batches {est['batches']:>3} | records {est['records_lower']:>6,} to {est['records_upper']:>6,}"
              f" | requests {est['pages_lower']:>4} to {est['pages_upper']:>4}")
    print(f"  {'TOTAL requests':<18} {totals['lower']} to {totals['upper']}")


def print_lengths(docs):
    lengths = [markers.window_days(d["trend_windows"]["w1"]) for d in docs]
    dist = markers.length_distribution(lengths)
    print("\nw1 length in days (min / median / p95 / max): "
          f"{dist['min']} / {dist['median']:g} / {dist['p95']} / {dist['max']}")
    by_source = Counter(str(d["marker_source"]["w1"]) for d in docs)
    print("w1 by source: " + ", ".join(f"{k} {v}" for k, v in sorted(by_source.items())))
    for source in sorted(by_source):
        part = [markers.window_days(d["trend_windows"]["w1"]) for d in docs if str(d["marker_source"]["w1"]) == source]
        d2 = markers.length_distribution(part)
        print(f"  {source:<20} n={len(part):>4}  min {d2['min']}, median {d2['median']:g}, p95 {d2['p95']}, max {d2['max']}")


def main():
    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)
    fields = {"collection_status": 1, "trend_windows": 1, "marker_source": 1}
    with_markers = list(database[candidates.COLLECTION].find(
        {"eligible": True, "markers_fetched_at": {"$exists": True}}, fields))
    status = Counter(d["collection_status"] for d in with_markers)
    print("Candidates with markers: " + ", ".join(f"{k} {v}" for k, v in sorted(status.items())))
    ready = [d for d in with_markers if d["collection_status"] == "ready"]
    pending = [d for d in with_markers if d["collection_status"] == "pending"]
    if not ready:
        print("No ready candidates yet. Run: python -m scripts.collect_airing_markers")
        return
    print_estimate("READY shows only", ready)
    if pending:
        print_estimate("READY + PENDING shows (pending ones can be collected once their finale + 9 days has passed)",
                       ready + pending)
    print_lengths(ready)
    print("\n(0 AniList requests used.)")


if __name__ == "__main__":
    try:
        main()
    except (config.ConfigError,) as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nStopped: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
