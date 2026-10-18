"""Model A baselines on train and validation. The test split is NOT loaded. 0 AniList requests.

Run from the episode-three folder:
    python -m scripts.evaluate_model_a_baselines

Prints the table (B1 finale = ep3 score, B2 train mean, B3 linear regression), B3's coefficient and intercept,
and B1's validation breakdowns, and writes reports/model_a_baselines_v1.json. The file has no timestamps: same
code + same data gives an identical file (git history says when it was made).
"""
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

# Lets "python scripts\evaluate_model_a_baselines.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from episode_three import anilist_sync, config, db
from episode_three.models import data_a, report_a

REPORT = PROJECT_ROOT / "reports" / "model_a_baselines_v1.json"
CODE_PATHS = ("episode_three", "scripts", "requirements.txt")
LIBRARIES = ("numpy", "pandas", "scikit-learn", "scipy")


def code_commit():
    """The last commit that changed code (not reports, docs or devlogs), plus -dirty if code has uncommitted edits.

    Not plain HEAD: committing the report itself would move HEAD, and re-running would then change the file.
    """
    def git(*args):
        return subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    commit = git("log", "-1", "--format=%H", "--", *CODE_PATHS)
    dirty = git("status", "--porcelain", "--", *CODE_PATHS)
    return commit + ("-dirty" if dirty else "")


def versions():
    return {"python": ".".join(map(str, sys.version_info[:3])), **{name: version(name) for name in LIBRARIES}}


def print_breakdown(report):
    print("\nB1 validation MAE by group (descriptive only; nothing is tuned on it):")
    b = report["validation_breakdown"]

    def line(label, group):
        mae = "-" if group["mae"] is None else f"{group['mae']:.2f}"
        print(f"  {label:<40} n = {group['n']:>3}   MAE {mae}")
    for fmt, group in b["b1_by_format"].items():
        line(f"format {fmt}", group)
    for key, group in b["b1_by_sequel"].items():
        line(key.replace("_", "-"), group)
    for flag, groups in b["b1_by_flag"].items():
        line(f"{flag}: flagged", groups["flagged"])
        line(f"{flag}: without the flagged", groups["unflagged"])


def main():
    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)
    documents = data_a.load_documents(("train", "validation"), database=database)   # the test split is never requested
    frames = data_a.to_frames(documents)
    report = report_a.build_report(
        frames["train"], frames["validation"], code_commit(), data_a.data_fingerprint(documents),
        ("train", "validation"), versions())
    print(f"\nTrain {report['rows']['train']} shows, validation {report['rows']['validation']} shows. "
          "Test split not loaded.\n")
    print("\n".join(report_a.table_lines(report)))
    f = report["fitted"]
    print(f"\nB2 train mean: {f['b2_train_mean']:.2f}")
    print(f"B3: y = {f['b3_intercept']:.4f} + {f['b3_coefficient']:.4f} * ep3_score")
    print_breakdown(report)
    REPORT.write_text(report_a.render(report), encoding="utf-8", newline="\n")
    print(f"\nWrote {REPORT.relative_to(PROJECT_ROOT)} (code_commit {report['code_commit'][:10]}, "
          f"data_fingerprint {report['data_fingerprint'][:12]}...)")
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
