"""Flag shows whose trend markers and schedule markers disagree by more than a day. 0 requests.

Run from the episode-three folder:
    python -m scripts.flag_marker_disagreement

For every show with w1 data it compares the trend marker (first record with episode = n) with the
schedule marker for n = 1..4 and writes two fields on model_a_candidates:
    markers.flags.marker_disagreement   true if any episode differs by more than one day
    markers.disagreement_episodes       which episodes
Model A is later trained with and without these shows (a sensitivity), so nothing is excluded here.
Safe to re-run: it recomputes the same values.
"""
import sys
from collections import Counter
from pathlib import Path

# Lets "python scripts\flag_marker_disagreement.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import UpdateOne

from episode_three import anilist_sync, config, db
from episode_three.collect import model_a_candidates as candidates
from episode_three.collect import score_trends as trends


def main():
    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)

    snapshots_by_id = {t["_id"]: t.get("snapshots_w1", [])
                       for t in database[trends.COLLECTION].find({}, {"snapshots_w1": 1})}
    shows = list(database[candidates.COLLECTION].find(
        {"eligible": True, "w1_status": "collected"}, {"markers": 1}))
    updates, flagged, by_episode = [], 0, Counter()
    for show in shows:
        episodes = trends.marker_disagreement(snapshots_by_id.get(show["_id"], []), show["markers"]["schedule"])
        if episodes:
            flagged += 1
            by_episode.update(episodes)
        updates.append(UpdateOne({"_id": show["_id"]}, {"$set": {
            "markers.flags.marker_disagreement": bool(episodes), "markers.disagreement_episodes": episodes}}))
    if updates:
        database[candidates.COLLECTION].bulk_write(updates, ordered=False)
    print(f"Shows checked: {len(shows)}; marker_disagreement: {flagged} ({flagged / len(shows):.1%})")
    print("Episodes involved (a show can have several): " + (
        ", ".join(f"ep{n} {by_episode[n]}" for n in sorted(by_episode)) or "none"))
    print("(0 AniList requests used.)")


if __name__ == "__main__":
    try:
        main()
    except config.ConfigError as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nStopped: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
