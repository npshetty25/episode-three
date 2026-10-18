"""The final Model A evaluation: the pre-registration lock, the run-once guard, the refit and the test scoring.

Everything here is pure or touches only local files and git; the one script that loads the test split is
scripts/evaluate_model_a_final.py. The lock file is the plan, committed BEFORE any test row is loaded; the
evaluation reads its configuration from it, so it cannot drift from what was registered.
"""
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from episode_three.models import features_a, select_a, train_a
from episode_three.models.report_a import r

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOCK_PATH = PROJECT_ROOT / "reports" / "model_a_test_lock.json"
REPORT_JSON = PROJECT_ROOT / "reports" / "model_a_v1.json"
REPORT_MD = PROJECT_ROOT / "reports" / "model_a_v1.md"
CRITERION_PCT = 10          # spec section 7: test MAE at least 10% below B1

# What the report must contain; written into the lock, checked after the evaluation.
PLANNED_SECTIONS = ("primary", "paired", "criterion", "sensitivity.per_season", "sensitivity.by_format",
                    "sensitivity.by_sequel", "sensitivity.excluding_flagged", "sensitivity.secondary_label",
                    "largest_errors")
FLAG_GROUPS = {"marker_disagreement": ("marker_disagreement",), "label_offset_unusual": ("label_offset_unusual",),
               "m1_unknown": ("m1_unknown",), "fallback_windows": ("fallback_w1", "fallback_w2")}


class LockError(Exception):
    """The pre-registration lock is missing, uncommitted or does not match the data."""


class AlreadyEvaluated(Exception):
    """The final report exists and no --rerun-reason was given."""


# --- the lock ---------------------------------------------------------------------------------------------------

def build_lock(selection_report, trainval_fingerprint, rows, code_commit):
    """The pre-registration document. Deterministic: no timestamps (git records when it was committed)."""
    extension = selection_report["ridge_alpha_extension"]
    chosen = selection_report["chosen_family"]
    if chosen != "ridge":
        raise LockError(f"the selection report chose {chosen!r}; TASK 014 locks Ridge")
    return {
        "purpose": "Pre-registration of the Model A final evaluation. Committed BEFORE any test row is loaded.",
        "family": "ridge", "alpha": extension["chosen_alpha"], "popularity_variant": extension["popularity_variant"],
        "alpha_selection": {"source": "reports/model_a_selection_v1.json (ridge_alpha_extension)", "grid": extension["alphas"],
                            "cv_best_alpha": extension["chosen_alpha"], "chosen_at_boundary": extension["chosen_at_boundary"],
                            "rule": "lowest mean time-CV MAE inside train; family and popularity variant not reopened"},
        "target": "delta = finale - ep3_score; prediction = clip(ep3_score + delta, 0, 100)",
        "features": features_a.INPUT_COLUMNS,
        "preprocessing": ["numeric: SimpleImputer(median, add_indicator=True) then StandardScaler (Ridge)",
                          "format, source_material: OneHotEncoder(handle_unknown=ignore)",
                          "genres: multi-hot, vocabulary from the fitting rows, unseen genres ignored",
                          "log1p for popularity and in-progress counts", "all fitted on train + validation rows only"],
        "final_fit": {"rows": rows, "refit": "Ridge pipeline, B2 mean and B3 linear fit on train + validation; B1 needs no fit"},
        "planned_metrics": {"models": ["B1", "B2", "B3", "ridge"], "metrics": ["MAE with bootstrap 95% CI", "RMSE", "within +-3"],
                            "paired": ["ridge - B1", "ridge - B3"], "bootstrap": {"resamples": 1000, "seed": 42, "level": 95}},
        "criterion": f"PASS if test MAE of Ridge is at least {CRITERION_PCT}% below the test MAE of B1, else FAIL",
        "planned_sensitivity": {
            "per_test_season": "n, Ridge MAE, B1 MAE", "format": "TV vs ONA", "sequel": "sequel vs non-sequel",
            "excluding_flagged": "each of marker_disagreement, label_offset_unusual, m1_unknown, fallback windows, and all together",
            "secondary_label": "same predictions scored against the finale + 5..9 label, shows that have one, Ridge and B1",
            "largest_errors": "the 10 largest Ridge errors: id, romaji title, season, ep3, prediction, label"},
        "planned_report_sections": list(PLANNED_SECTIONS),
        "run_once": "reports/model_a_v1.json is written once; a rerun needs --rerun-reason and is stored in the report",
        "code_commit": code_commit, "trainval_data_fingerprint": trainval_fingerprint,
        "test_split": "not loaded when this lock was written",
    }


def lock_sha256(path=LOCK_PATH):
    """sha256 of the lock file with line endings normalised (so Windows checkouts hash the same)."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _git(*args):
    done = subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True)
    return done.returncode, done.stdout.strip()


def check_lock(lock_path=LOCK_PATH, git=_git):
    """The lock must exist AND be committed with no uncommitted changes. Returns the lock as a dict."""
    lock_path = Path(lock_path)
    if not lock_path.exists():
        raise LockError(f"{lock_path.name} does not exist: run scripts.lock_model_a_test and commit it first.")
    relative = lock_path.relative_to(PROJECT_ROOT).as_posix() if lock_path.is_absolute() and PROJECT_ROOT in lock_path.parents else lock_path.name
    code, _ = git("ls-files", "--error-unmatch", "--", relative)
    if code != 0:
        raise LockError(f"{lock_path.name} is not committed: commit it BEFORE any test row is loaded.")
    code, changes = git("status", "--porcelain", "--", relative)
    if code != 0 or changes:
        raise LockError(f"{lock_path.name} has uncommitted changes: commit it unchanged before the evaluation.")
    return json.loads(lock_path.read_text(encoding="utf-8"))


def check_run_once(report_path=REPORT_JSON, rerun_reason=None):
    """(run_count, rerun_reasons) for this run, or AlreadyEvaluated if the report exists and no reason was given."""
    report_path = Path(report_path)
    if not report_path.exists():
        return 1, []
    if not rerun_reason:
        raise AlreadyEvaluated('already evaluated (reports/model_a_v1.json exists); use --rerun-reason "<text>" '
                               "and report the rerun to the instructor.")
    previous = json.loads(report_path.read_text(encoding="utf-8"))
    return previous.get("run_count", 1) + 1, list(previous.get("rerun_reasons", [])) + [rerun_reason]


# --- refit and evaluate -------------------------------------------------------------------------------------------

def refit(fit_frame, lock):
    """Ridge pipeline, B2 mean and B3 fitted on the given rows (train + validation in the real run)."""
    family, variant = lock["family"], lock["popularity_variant"]
    ridge = train_a.fit_family(family, {"model__alpha": lock["alpha"]}, variant, fit_frame)
    b3 = LinearRegression().fit(fit_frame[["ep3_score"]].to_numpy(dtype=float), fit_frame["y"].to_numpy(dtype=float))
    return {"ridge": ridge, "b2_mean": float(fit_frame["y"].mean()), "b3": b3, "n_fit": int(len(fit_frame)),
            "variant": variant, "b3_coefficient": float(b3.coef_[0]), "b3_intercept": float(b3.intercept_)}


def predictions(fitted, frame):
    X, _, _ = features_a.build_xy(frame, fitted["variant"])
    return {"B1": frame["ep3_score"].to_numpy(dtype=float),
            "B2": np.full(len(frame), fitted["b2_mean"]),
            "B3": fitted["b3"].predict(frame[["ep3_score"]].to_numpy(dtype=float)),
            "ridge": train_a.predict_finale(fitted["ridge"], X)}


def _mae(truth, prediction):
    return float(np.mean(np.abs(truth - prediction))) if len(truth) else None


def group_row(mask, truth, pred):
    mask = np.asarray(mask, dtype=bool)
    return {"n": int(mask.sum()), "ridge_mae": r(_mae(truth[mask], pred["ridge"][mask])), "b1_mae": r(_mae(truth[mask], pred["B1"][mask]))}


def season_label(year, season):
    return f"{season.title()} {year}"


def evaluate(frame, pred):
    """All planned outputs for one frame (the test split in the real run). Pure."""
    truth = frame["y"].to_numpy(dtype=float)
    primary = {name: select_a.validation_scores(truth, pred[name], {}) for name in ("B1", "B2", "B3")}
    ridge = select_a.validation_scores(truth, pred["ridge"], {"B1": pred["B1"], "B3": pred["B3"]})
    primary["ridge"] = {k: v for k, v in ridge.items() if not k.startswith("diff_vs")}
    paired = {"ridge_minus_b1": ridge["diff_vs_b1"], "ridge_minus_b3": ridge["diff_vs_b3"]}

    b1_mae, ridge_mae = _mae(truth, pred["B1"]), _mae(truth, pred["ridge"])
    reduction = 100 * (1 - ridge_mae / b1_mae)
    criterion = {"b1_mae": r(b1_mae), "ridge_mae": r(ridge_mae), "reduction_pct": r(reduction),
                 "required_pct": CRITERION_PCT, "result": "PASS" if ridge_mae <= (1 - CRITERION_PCT / 100) * b1_mae else "FAIL"}

    seasons = sorted(set(zip(frame["season_year"], frame["season"])), key=lambda k: (k[0], ["WINTER", "SPRING", "SUMMER", "FALL"].index(k[1])))
    per_season = [{"season": season_label(y, s), **group_row((frame["season_year"] == y) & (frame["season"] == s), truth, pred)}
                  for y, s in seasons]
    by_format = {str(f): group_row(frame["format"] == f, truth, pred) for f in sorted(frame["format"].dropna().unique())}
    sequel = frame["is_sequel"].astype(bool).to_numpy()
    by_sequel = {"sequel": group_row(sequel, truth, pred), "non_sequel": group_row(~sequel, truth, pred)}

    flagged_any = np.zeros(len(frame), dtype=bool)
    excluding = {}
    for name, columns in FLAG_GROUPS.items():
        flagged = np.any([frame[c].astype(bool).to_numpy() for c in columns], axis=0)
        flagged_any |= flagged
        excluding[name] = {"flagged": int(flagged.sum()), "remaining": group_row(~flagged, truth, pred)}
    excluding["all_together"] = {"flagged": int(flagged_any.sum()), "remaining": group_row(~flagged_any, truth, pred)}

    secondary = frame["y_secondary"].to_numpy(dtype=float)
    has = ~np.isnan(secondary)
    secondary_label = {"n": int(has.sum()), "without_secondary_label": int((~has).sum()),
                       "ridge_mae_vs_secondary": r(_mae(secondary[has], pred["ridge"][has])),
                       "b1_mae_vs_secondary": r(_mae(secondary[has], pred["B1"][has])),
                       "ridge_mae_vs_primary_same_shows": r(_mae(truth[has], pred["ridge"][has])),
                       "b1_mae_vs_primary_same_shows": r(_mae(truth[has], pred["B1"][has]))}

    errors = np.abs(truth - pred["ridge"])
    order = sorted(range(len(frame)), key=lambda i: (-errors[i], frame["_id"].iloc[i]))[:10]
    largest = [{"id": frame["_id"].iloc[i], "title": frame["title_romaji"].iloc[i] if "title_romaji" in frame else None,
                "season": season_label(frame["season_year"].iloc[i], frame["season"].iloc[i]),
                "ep3_score": r(frame["ep3_score"].iloc[i]), "prediction": r(pred["ridge"][i]), "label": r(truth[i]),
                "abs_error": r(errors[i])} for i in order]
    return {"primary": primary, "paired": paired, "criterion": criterion,
            "sensitivity": {"per_season": per_season, "by_format": by_format, "by_sequel": by_sequel,
                            "excluding_flagged": excluding, "secondary_label": secondary_label},
            "largest_errors": largest}


def missing_sections(report, planned=PLANNED_SECTIONS):
    """Planned report sections the report does not contain (must be empty)."""
    missing = []
    for path in planned:
        node = report
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                missing.append(path)
                break
            node = node[key]
    return missing


def build_report(results, lock, lock_hash, fit_info, eval_info, run_count, rerun_reasons, code_commit, versions):
    report = {
        "model": "Model A v1: Ridge on delta (finale - ep3 score)", "family": lock["family"], "alpha": lock["alpha"],
        "popularity_variant": lock["popularity_variant"], "features": lock["features"], "target": lock["target"],
        "data_window": {"fit": fit_info["seasons"], "evaluated": eval_info["seasons"]},
        "rows": {"fit": fit_info["rows"], "evaluated": eval_info["rows"]},
        "fitted": {"b2_mean": r(fit_info["b2_mean"]), "b3_coefficient": r(fit_info["b3_coefficient"]),
                   "b3_intercept": r(fit_info["b3_intercept"])},
        **results,
        "code_commit": code_commit, "library_versions": dict(sorted(versions.items())),
        "trainval_data_fingerprint": lock["trainval_data_fingerprint"], "test_data_fingerprint": eval_info["fingerprint"],
        "lock_sha256": lock_hash, "run_count": run_count, "rerun_reasons": rerun_reasons,
    }
    gaps = missing_sections(report, lock["planned_report_sections"])
    assert not gaps, f"the report lacks planned sections: {gaps}"
    return report


def season_span(frame):
    keys = sorted(set(zip(frame["season_year"], frame["season"])), key=lambda k: (k[0], ["WINTER", "SPRING", "SUMMER", "FALL"].index(k[1])))
    return f"{season_label(*keys[0])} to {season_label(*keys[-1])}" if keys else "-"


def render_json(report):
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


# --- printing and the human-readable report -----------------------------------------------------------------------------

def result_lines(report):
    c = report["criterion"]
    lines = [f"{'model':<8}{'MAE':>6} {'MAE 95% CI':<16}{'RMSE':>6}{'within +-3':>12}"]
    for name in ("B1", "B2", "B3", "ridge"):
        p = report["primary"][name]
        lines.append(f"{name:<8}{p['mae']:>6.2f} [{p['mae_ci95'][0]:.2f}, {p['mae_ci95'][1]:.2f}]  {p['rmse']:>6.2f}{p['within_3']:>11.1f}%")
    for key, label in (("ridge_minus_b1", "Ridge - B1"), ("ridge_minus_b3", "Ridge - B3")):
        d = report["paired"][key]
        lines.append(f"paired {label}: {d['mean']:+.3f} [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}]  "
                     + ("(entirely below 0)" if d["better"] else "(interval includes 0 or is above it)"))
    lines += ["", f"CRITERION (test MAE at least {c['required_pct']}% below B1): Ridge {c['ridge_mae']:.2f} vs B1 {c['b1_mae']:.2f} "
              f"= {c['reduction_pct']:.1f}% lower -> {c['result']}", "", "Per test season (n, Ridge MAE, B1 MAE):"]
    for row in report["sensitivity"]["per_season"]:
        lines.append(f"  {row['season']:<14}{row['n']:>4}  {row['ridge_mae']:>5.2f}  {row['b1_mae']:>5.2f}")
    lines.append("By format / sequel:")
    groups = {**{f"format {k}": v for k, v in report["sensitivity"]["by_format"].items()},
              **{k.replace("_", "-"): v for k, v in report["sensitivity"]["by_sequel"].items()}}
    for name, g in groups.items():
        lines.append(f"  {name:<14}{g['n']:>4}  {g['ridge_mae']:>5.2f}  {g['b1_mae']:>5.2f}")
    lines.append("Excluding flagged shows (flagged, remaining n, Ridge MAE, B1 MAE):")
    for name, g in report["sensitivity"]["excluding_flagged"].items():
        rem = g["remaining"]
        lines.append(f"  {name:<22}{g['flagged']:>4}  {rem['n']:>4}  {rem['ridge_mae']:>5.2f}  {rem['b1_mae']:>5.2f}")
    s = report["sensitivity"]["secondary_label"]
    lines += [f"Secondary label (finale + 5..9 days), {s['n']} shows have one ({s['without_secondary_label']} do not): "
              f"Ridge MAE {s['ridge_mae_vs_secondary']:.2f}, B1 MAE {s['b1_mae_vs_secondary']:.2f} "
              f"(same shows against the primary label: Ridge {s['ridge_mae_vs_primary_same_shows']:.2f}, B1 {s['b1_mae_vs_primary_same_shows']:.2f})",
              "", "The 10 largest Ridge errors:", f"  {'id':<15}{'season':<14}{'ep3':>5}{'pred':>7}{'label':>7}{'|err|':>7}  title"]
    for e in report["largest_errors"]:
        lines.append(f"  {e['id']:<15}{e['season']:<14}{e['ep3_score']:>5.0f}{e['prediction']:>7.1f}{e['label']:>7.0f}{e['abs_error']:>7.2f}  {e['title']}")
    return lines


def render_md(report):
    c, p = report["criterion"], report["primary"]
    ci = lambda m: f"{m['mae']:.2f} [{m['mae_ci95'][0]:.2f}, {m['mae_ci95'][1]:.2f}]"
    lines = ["# Model A v1: final test result", "",
             f"Ridge (alpha {report['alpha']}, popularity {report['popularity_variant']}) predicts the change from the episode-3 score to the "
             f"finale score. Fitted on {report['rows']['fit']} shows ({report['data_window']['fit']}), scored once on "
             f"{report['rows']['evaluated']} test shows ({report['data_window']['evaluated']}).", "",
             "| Model | MAE [95% CI] | RMSE | within ±3 |", "|---|---|---:|---:|"]
    for name in ("B1", "B2", "B3", "ridge"):
        lines.append(f"| {name} | {ci(p[name])} | {p[name]['rmse']:.2f} | {p[name]['within_3']:.1f}% |")
    d1, d3 = report["paired"]["ridge_minus_b1"], report["paired"]["ridge_minus_b3"]
    lines += ["", f"Paired difference in absolute error (Ridge minus baseline): vs B1 {d1['mean']:+.3f} "
              f"[{d1['ci95'][0]:+.3f}, {d1['ci95'][1]:+.3f}], vs B3 {d3['mean']:+.3f} [{d3['ci95'][0]:+.3f}, {d3['ci95'][1]:+.3f}].", "",
              f"**Criterion (test MAE at least {c['required_pct']}% below B1): {c['result']}.** "
              f"Ridge {c['ridge_mae']:.2f} vs B1 {c['b1_mae']:.2f}, {c['reduction_pct']:.1f}% lower.", "",
              "## README results row", "",
              "| Model | Test MAE [95% CI] | B1 (finale = ep3) | Improvement | 10% criterion |", "|---|---|---|---|---|",
              f"| Model A v1 (Ridge, alpha {report['alpha']}) | {ci(p['ridge'])} | {p['B1']['mae']:.2f} | "
              f"{c['reduction_pct']:.1f}% | {c['result']} |", "",
              "Full numbers, the sensitivity tables and the ten largest errors are in `model_a_v1.json`.",
              f"Code commit `{report['code_commit'][:10]}`, lock `{report['lock_sha256'][:12]}`, run count {report['run_count']}.", ""]
    return "\n".join(lines)
