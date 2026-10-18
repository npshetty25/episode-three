"""The Model A final evaluation: refit on train + validation, score the locked test split ONCE.

Run from the episode-three folder:
    python -m scripts.evaluate_model_a_final
    python -m scripts.evaluate_model_a_final --rehearsal      # same code on validation (fit on train); loads NO test rows, writes nothing

Order of events: (1) the pre-registration lock must exist and be committed; (2) the run-once guard: if
reports/model_a_v1.json exists the script stops unless --rerun-reason "<text>" is given (stored in the report;
report any rerun to the instructor); (3) only then is the test split loaded. This is the only place in the codebase
that sets the allow_test flag. Writes reports/model_a_v1.json, reports/model_a_v1.md and
artifacts/models/model_a_v1.joblib (git-ignored). No timestamps in the reports. 0 AniList requests.
"""
import argparse
import sys
from pathlib import Path

# Lets "python scripts\evaluate_model_a_final.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import pandas as pd

from episode_three import anilist_sync, config, db
from episode_three.models import data_a, final_a, run_info

ARTIFACT = PROJECT_ROOT / "artifacts" / "models" / "model_a_v1.joblib"


def main():
    parser = argparse.ArgumentParser(description="Model A final evaluation on the locked test split (run once).")
    parser.add_argument("--rerun-reason", help="required to run again once reports/model_a_v1.json exists")
    parser.add_argument("--rehearsal", action="store_true", help="evaluate on validation instead of test; writes nothing")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")

    lock = final_a.check_lock()                                   # (1) the plan is committed
    print(f"Lock OK: Ridge, alpha {lock['alpha']}, popularity {lock['popularity_variant']}, lock {final_a.lock_sha256()[:12]}...")
    run_count, reasons = (1, []) if args.rehearsal else final_a.check_run_once(rerun_reason=args.rerun_reason)   # (2) run once

    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)
    documents = data_a.load_documents(("train", "validation"), database=database)
    frames = data_a.to_frames(documents)
    fingerprint = data_a.data_fingerprint(documents)
    if fingerprint != lock["trainval_data_fingerprint"]:
        raise final_a.LockError("train + validation data differ from the locked fingerprint: stop and tell the instructor.")

    if args.rehearsal:
        fit_frame, eval_frame, eval_fingerprint = frames["train"], frames["validation"], None
        print("REHEARSAL: fit on train, evaluate on validation. The test split is NOT loaded.")
    else:
        fit_frame = pd.concat([frames["train"], frames["validation"]], ignore_index=True)
        assert len(fit_frame) == lock["final_fit"]["rows"]["total"], "the refit must use exactly the locked train + validation rows"
        print("Loading the test split: the one allowed load.")
        test_documents = data_a.load_documents(("test",), allow_test=True, database=database)   # (3) the only test load
        eval_frame = data_a.to_frames(test_documents)["test"]
        eval_fingerprint = data_a.data_fingerprint(test_documents)
    print(f"Fit on {len(fit_frame)} shows ({final_a.season_span(fit_frame)}); evaluating {len(eval_frame)} shows "
          f"({final_a.season_span(eval_frame)}).\n")

    fitted = final_a.refit(fit_frame, lock)
    results = final_a.evaluate(eval_frame, final_a.predictions(fitted, eval_frame))
    report = final_a.build_report(
        results, lock, final_a.lock_sha256(),
        {"rows": fitted["n_fit"], "seasons": final_a.season_span(fit_frame), "b2_mean": fitted["b2_mean"],
         "b3_coefficient": fitted["b3_coefficient"], "b3_intercept": fitted["b3_intercept"]},
        {"rows": len(eval_frame), "seasons": final_a.season_span(eval_frame), "fingerprint": eval_fingerprint},
        run_count, reasons, run_info.code_commit(), run_info.versions())
    print("\n".join(final_a.result_lines(report)))

    if args.rehearsal:
        print("\nRehearsal only: nothing written, nothing locked in. Test split not loaded. (0 AniList requests used.)")
        return
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"family": "ridge", "alpha": lock["alpha"], "popularity_variant": lock["popularity_variant"],
                 "model": fitted["ridge"], "fit_on": "train + validation"}, ARTIFACT)
    final_a.REPORT_JSON.write_text(final_a.render_json(report), encoding="utf-8", newline="\n")
    final_a.REPORT_MD.write_text(final_a.render_md(report), encoding="utf-8", newline="\n")
    print(f"\nWrote reports/model_a_v1.json, reports/model_a_v1.md and {ARTIFACT.relative_to(PROJECT_ROOT)} (git-ignored).")
    print(f"Test split loaded {run_count} time(s) in total across runs (this run: 1). (0 AniList requests used.)")


if __name__ == "__main__":
    try:
        main()
    except (config.ConfigError, final_a.LockError, final_a.AlreadyEvaluated) as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nStopped: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
