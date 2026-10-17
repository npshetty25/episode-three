"""Compare the trend episode markers with the schedule markers. 0 requests.

Run from the episode-three folder:
    python -m scripts.check_trend_markers

For each collected show: the trend marker for episode n (n = 1..4) is the day of the first trend
record whose `episode` equals n; the schedule marker comes from the airing schedule (TASK 008).
Prints how far apart they are, how many fallback shows are rescued by trend markers, and how many
shows cannot give an episode-3 snapshot (and why).
"""
import sys
from collections import Counter
from pathlib import Path

# Lets "python scripts\check_trend_markers.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from episode_three import anilist_sync, config, db
from episode_three.collect import model_a_candidates as candidates
from episode_three.collect import score_trends as trends


def print_differences(differences):
    all_diffs = [d for per_episode in differences.values() for d in per_episode]
    print("\nTrend marker minus schedule marker, in days (shows with both):")
    if not all_diffs:
        print("  no comparable markers yet")
        return
    counts = Counter(all_diffs)
    for value in sorted(counts):
        print(f"  {value:+d} day(s): {counts[value]:>5}  ({counts[value] / len(all_diffs):.1%})")
    within = sum(1 for d in all_diffs if abs(d) <= 1)
    print(f"  Within +-1 day: {within} of {len(all_diffs)} ({within / len(all_diffs):.1%}); "
          f"exactly 0: {counts[0]} ({counts[0] / len(all_diffs):.1%})")
    for n in (1, 2, 3, 4):
        diffs = differences[n]
        if diffs:
            ok = sum(1 for d in diffs if abs(d) <= 1)
            print(f"  episode {n}: {len(diffs):>5} compared, {ok / len(diffs):.1%} within +-1 day")


def main():
    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)

    shows = list(database[candidates.COLLECTION].find(
        {"eligible": True, "collection_status": "ready"},
        {"markers": 1, "marker_source": 1, "w1_status": 1, "start_date": 1, "end_date": 1}))
    snapshots_by_id = {t["_id"]: t.get("snapshots_w1", [])
                       for t in database[trends.COLLECTION].find({}, {"snapshots_w1": 1})}
    collected = [s for s in shows if s.get("w1_status") == "collected"]
    print(f"Ready shows: {len(shows)}; w1 collected: {len(collected)}; "
          f"no_records: {sum(1 for s in shows if s.get('w1_status') == 'no_records')}; "
          f"not yet collected: {sum(1 for s in shows if 'w1_status' not in s)}")

    differences = {n: [] for n in (1, 2, 3, 4)}
    present = Counter()
    fallback = rescued = rescued_all_four = m1_unknown = 0
    reasons = Counter()
    reasons_by_source = {"schedule": Counter(), "fallback_start_date": Counter()}
    for show in collected:
        snapshots = snapshots_by_id.get(show["_id"], [])
        trend_days = trends.trend_marker_days(snapshots)
        schedule = show["markers"]["schedule"]
        for n in (1, 2, 3, 4):
            if trend_days[n] is not None:
                present[n] += 1
                if schedule[f"ep{n}"] is not None:
                    differences[n].append(trends.day_difference(trend_days[n], schedule[f"ep{n}"]))
        source = show["marker_source"]["w1"]
        if source == "fallback_start_date":
            fallback += 1
            if trend_days[3] is not None and trend_days[4] is not None:
                rescued += 1
            if all(trend_days[n] is not None for n in (1, 2, 3, 4)):
                rescued_all_four += 1
        m1 = trends.earliest(schedule["ep1"], trend_days[1])
        if m1 is None:
            m1_unknown += 1  # ep1 features become null, but the show is kept
        m3 = trends.earliest(schedule["ep3"], trend_days[3])
        m4 = trends.earliest(schedule["ep4"], trend_days[4])
        ok, reason = trends.ep3_snapshot_check(snapshots, m3, m4)
        if not ok and trends.is_binge(show):
            reason = "m3_not_before_m4 (binge)"  # released all at once: no M(3) < M(4)
        reasons[reason] += 1
        reasons_by_source.setdefault(source, Counter())[reason] += 1

    print("\nTrend markers present (a record with episode = n inside w1): "
          + ", ".join(f"ep{n} {present[n]}" for n in (1, 2, 3, 4)) + f" of {len(collected)} shows")
    print_differences(differences)
    print(f"\nFallback shows (w1 from the start date): {fallback}")
    print(f"  rescued by trend markers (episodes 3 AND 4 both present): {rescued}; all of episodes 1-4: {rescued_all_four}")
    print("\nEpisode-3 snapshot check, M(n) = earliest of schedule and trend marker:")
    for reason in ("ok", "no_scored_record", "m3_not_before_m4", "m3_not_before_m4 (binge)", "no_m3", "no_m4"):
        print(f"  {reason:<26} {reasons[reason]:>5}")
    lacking = len(collected) - reasons["ok"]
    print(f"  shows lacking an ep3 snapshot: {lacking} of {len(collected)}")
    print(f"\nm1_unknown (no M(1) from the schedule or the trend records; ep1 features null, show kept): "
          f"{m1_unknown} of {len(collected)}")
    for source, counter in reasons_by_source.items():
        if counter:
            print(f"    {source:<20} " + ", ".join(f"{k} {v}" for k, v in sorted(counter.items())))
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
