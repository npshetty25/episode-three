"""Write the pre-registration lock for the Model A final evaluation. The test split is NOT loaded. 0 requests.

Run from the episode-three folder:
    python -m scripts.lock_model_a_test
    git add reports/model_a_test_lock.json
    git commit -m "TASK 014: test lock (pre-registration)"

The lock holds the final configuration (family, alpha, popularity variant, features, preprocessing), the planned
metrics and sensitivity analyses, the code commit and the train + validation data fingerprint. The final
evaluation refuses to run unless this file exists and is committed. An existing lock is never overwritten.
"""
import json
import sys
from pathlib import Path

# Lets "python scripts\lock_model_a_test.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from episode_three import anilist_sync, config, db
from episode_three.models import data_a, final_a, run_info

SELECTION = PROJECT_ROOT / "reports" / "model_a_selection_v1.json"


def main():
    if final_a.LOCK_PATH.exists():
        print(f"{final_a.LOCK_PATH.relative_to(PROJECT_ROOT)} already exists: a lock is never overwritten. Nothing changed.")
        return
    commit = run_info.code_commit()
    if commit.endswith("-dirty"):
        raise config.ConfigError("code has uncommitted changes: commit them first, the lock is tied to a committed code state.")
    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)
    documents = data_a.load_documents(("train", "validation"), database=database)   # the test split is never requested
    frames = data_a.to_frames(documents)
    rows = {"train": len(frames["train"]), "validation": len(frames["validation"]),
            "total": len(frames["train"]) + len(frames["validation"])}
    lock = final_a.build_lock(json.loads(SELECTION.read_text(encoding="utf-8")), data_a.data_fingerprint(documents), rows, commit)
    final_a.LOCK_PATH.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"\nLocked: Ridge, alpha {lock['alpha']}, popularity {lock['popularity_variant']}, fit rows {rows['total']} "
          f"({rows['train']} train + {rows['validation']} validation).")
    print(f"code_commit {commit[:10]}, train+validation fingerprint {lock['trainval_data_fingerprint'][:12]}...")
    print(f"Wrote {final_a.LOCK_PATH.relative_to(PROJECT_ROOT)}. Now commit it, unchanged, BEFORE running the evaluation.")
    print("Test split not loaded. (0 AniList requests used.)")


if __name__ == "__main__":
    try:
        main()
    except config.ConfigError as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        sys.exit(1)
    except final_a.LockError as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nStopped: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
