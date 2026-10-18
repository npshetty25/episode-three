"""How many shows have a usable Model A label, and are the finales where we think they are? 0 requests.

Run from the episode-three folder:
    python -m scripts.check_labels

Reads snapshots_w2 (LABEL data) from score_trends; this script is analysis only, no feature code.
- primary label   = the last scored record with releasing = true (the finale day)
- secondary label = the scored record nearest to finale + 7 days, within finale + 5..9
- finale flags    = no_transition, finale_episode_mismatch, label_at_window_edge
The 78 shows whose finale came from the end date (fallback_end_date) are reported separately.
"""
import statistics
import sys
from collections import Counter
from pathlib import Path

# Lets "python scripts\check_labels.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from episode_three import anilist_sync, config, db
from episode_three.collect import model_a_candidates as candidates
from episode_three.collect import score_trends as trends

DAY = trends.DAY
FLAGS = ("no_transition", "finale_episode_mismatch", "label_at_window_edge")


def analyse(show, snapshots):
    """Labels and flags for one show (pure given its snapshots)."""
    finale_day = show["trend_windows"]["w2"]["from"] + DAY  # w2 starts one day before the finale
    primary = trends.find_primary_label(snapshots)
    secondary = trends.find_secondary_label(snapshots, finale_day)
    return {"primary": primary, "secondary": secondary, "flags": trends.finale_flags(snapshots, show["episodes"])}


def print_group(title, results):
    total = len(results)
    if not total:
        print(f"\n{title}: no shows")
        return
    primary = sum(1 for r in results if r["analysis"]["primary"])
    secondary = sum(1 for r in results if r["analysis"]["secondary"])
    both = sum(1 for r in results if r["analysis"]["primary"] and r["analysis"]["secondary"])
    neither = sum(1 for r in results if not r["analysis"]["primary"] and not r["analysis"]["secondary"])
    print(f"\n{title}: {total} shows")
    print(f"  primary label found:   {primary:>5} ({primary / total:.1%})")
    print(f"  secondary label found: {secondary:>5} ({secondary / total:.1%})")
    print(f"  both:                  {both:>5} ({both / total:.1%});  neither: {neither}")
    for flag in FLAGS:
        hits = [r for r in results if r["analysis"]["flags"][flag]]
        examples = ", ".join(r["show"]["_id"] for r in hits[:3])
        print(f"  flag {flag:<24} {len(hits):>5}" + (f"   e.g. {examples}" if hits else ""))
    disagree = [r for r in results if r["show"].get("markers", {}).get("flags", {}).get("marker_disagreement")]
    print(f"  marker_disagreement (|trend - schedule| > 1 day): {len(disagree)}")


def print_differences(results):
    diffs = [r["analysis"]["secondary"][0] - r["analysis"]["primary"][0] for r in results
             if r["analysis"]["primary"] and r["analysis"]["secondary"]]
    print("\nSecondary minus primary label, in points (shows with both):")
    if not diffs:
        print("  none yet")
        return
    counts = Counter(diffs)
    for value in sorted(counts):
        if abs(value) <= 6 or counts[value] >= 3:
            print(f"  {value:+d}: {counts[value]:>5} ({counts[value] / len(diffs):.1%})")
    abs_diffs = sorted(abs(d) for d in diffs)
    print(f"  n = {len(diffs)}; mean {statistics.mean(diffs):+.2f}, median {statistics.median(diffs):+g}; "
          f"mean |diff| {statistics.mean(abs_diffs):.2f}; within +-1: {sum(1 for d in abs_diffs if d <= 1) / len(diffs):.1%}, "
          f"within +-3: {sum(1 for d in abs_diffs if d <= 3) / len(diffs):.1%}; largest |diff| {abs_diffs[-1]}")


def main():
    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)

    shows = list(database[candidates.COLLECTION].find(
        {"eligible": True, "collection_status": "ready"},
        {"w1_status": 1, "w2_status": 1, "episodes": 1, "trend_windows": 1, "marker_source": 1, "markers": 1}))
    snapshots_by_id = {t["_id"]: t.get("snapshots_w2", [])
                       for t in database[trends.COLLECTION].find({"snapshots_w2": {"$exists": True}}, {"snapshots_w2": 1})}
    status = Counter(s.get("w2_status", "not collected") for s in shows)
    print("w2 status of the ready shows: " + ", ".join(f"{k} {v}" for k, v in sorted(status.items())))
    collected = [{"show": s, "analysis": analyse(s, snapshots_by_id.get(s["_id"], []))}
                 for s in shows if s.get("w2_status") == "collected"]
    schedule = [r for r in collected if r["show"]["marker_source"]["w2"] == "schedule"]
    fallback = [r for r in collected if r["show"]["marker_source"]["w2"] == "fallback_end_date"]
    print_group("All collected shows", collected)
    print_group("  of which finale from the schedule", schedule)
    print_group("  of which finale from the end date (fallback_end_date)", fallback)
    print_differences(collected)
    print("\n(0 AniList requests used.)")


if __name__ == "__main__":
    try:
        main()
    except config.ConfigError as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nStopped: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
