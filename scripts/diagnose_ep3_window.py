"""Would a wider ep3 window (K = 6, still floored at M(3) + 1) rescue the shows that have no ep3 snapshot? 0 requests.

Run from the episode-three folder (after build_model_a_features):
    python -m scripts.diagnose_ep3_window

Report only: nothing is changed or applied. Changing K is the instructor's decision, made before any training.
"""
import statistics
import sys
from pathlib import Path

# Lets "python scripts\diagnose_ep3_window.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from episode_three import anilist_sync, config, db
from episode_three.collect import score_trends as trends
from episode_three.features import model_a, model_a_report
from episode_three.features import model_a_pipeline as pipeline


def main():
    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)
    documents = list(database[pipeline.SNAPSHOTS].find({}))
    if not documents:
        raise config.ConfigError("model_a_snapshots is empty: run python -m scripts.build_model_a_features first.")
    w1 = {d["_id"]: d.get("snapshots_w1", []) for d in database[trends.COLLECTION].find({}, {"snapshots_w1": 1})}
    result = model_a_report.diagnose_k(documents, w1, k=6)
    rescued, passing = result["rescued"], result["passing"]
    print(f"\nShows with no ep3 snapshot under K = {model_a.K} (floored): {result['missing']}")
    for sub, count in sorted(result["subreasons"].items(), key=lambda kv: str(kv[0])):
        print(f"  {sub}: {count}")
    print(f"Rescued by K = 6 (a scored record in the floored 6-day window): {len(rescued)}")
    if rescued:
        pops = [p for _, p in rescued if p is not None]
        print(f"  their ep3 popularity: min {min(pops):,}, median {statistics.median(pops):,.0f}, max {max(pops):,}")
    print(f"  of those, passing the popularity filter (>= {model_a.POPULARITY_MIN:,}): {len(passing)}")
    for show_id, popularity in passing:
        print(f"    {show_id} (popularity {popularity:,})")
    print("\nNothing was applied. (0 AniList requests used.)")


if __name__ == "__main__":
    try:
        main()
    except config.ConfigError as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nStopped: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
