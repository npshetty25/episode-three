"""Train and compare the three Model A candidate families on validation. The test split is NOT loaded.

Run from the episode-three folder:
    python -m scripts.train_model_a

Hyperparameters and the popularity variant are chosen per family by expanding-window time CV inside train. The
chosen configuration of each family is refitted on train and compared ONCE on validation against B1 and B3 with
paired bootstrap CIs. Writes reports/model_a_selection_v1.json (no timestamps) and saves the fitted candidate to
artifacts/models/model_a_v1_candidate.joblib (git-ignored). 0 AniList requests.
"""
import sys
import time
from pathlib import Path

# Lets "python scripts\train_model_a.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json

import joblib

from episode_three import anilist_sync, config, db
from episode_three.models import data_a, run_info, select_a

REPORT = PROJECT_ROOT / "reports" / "model_a_selection_v1.json"
ARTIFACT = PROJECT_ROOT / "artifacts" / "models" / "model_a_v1_candidate.joblib"


def main():
    began = time.monotonic()
    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)
    documents = data_a.load_documents(("train", "validation"), database=database)   # the test split is never requested
    frames = data_a.to_frames(documents)
    train, validation = frames["train"], frames["validation"]
    print(f"Train {len(train)} shows, validation {len(validation)} shows. Test split not loaded.\n")

    def progress(result):
        print(f"  tuned {result['family']:<6} popularity={result['variant']:<10} best CV MAE {result['best_cv_mae']:.3f}", flush=True)

    print("Tuning (time CV inside train):")
    report, fitted = select_a.run_selection(train, validation, run_info.code_commit(), data_a.data_fingerprint(documents),
                                            ("train", "validation"), run_info.versions(), progress)
    print()
    print("\n".join(select_a.selection_lines(report)))

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    chosen = fitted["chosen"]
    joblib.dump({"family": chosen, "popularity_variant": fitted["variants"][chosen], "model": fitted["models"][chosen],
                 "fit_on": "train"}, ARTIFACT)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"\nSaved the chosen fitted pipeline to {ARTIFACT.relative_to(PROJECT_ROOT)} (git-ignored).")
    print(f"Wrote {REPORT.relative_to(PROJECT_ROOT)} (code_commit {report['code_commit'][:10]}, "
          f"data_fingerprint {report['data_fingerprint'][:12]}...)")
    print(f"Runtime: {time.monotonic() - began:.0f} s. Test split not loaded. (0 AniList requests used.)")


if __name__ == "__main__":
    try:
        main()
    except config.ConfigError as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nStopped: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
