"""Build the baseline report (a plain dict) and render it as JSON. Pure functions, deterministic.

No timestamps: the file says WHAT was run (code_commit, data_fingerprint, library versions); git history says when.
Same code + same data -> an identical file, byte for byte.
"""
import json

import numpy as np

from episode_three.models import baselines_a, metrics

ROUND = 4
FLAGS = ("marker_disagreement", "label_offset_unusual", "m1_unknown")


def r(value):
    return None if value is None else round(float(value), ROUND)


def scores(y_true, y_pred):
    return {"mae": r(metrics.mae(y_true, y_pred)), "rmse": r(metrics.rmse(y_true, y_pred)),
            "within_3": r(metrics.pct_within(y_true, y_pred, 3))}


def group_mae(frame, mask):
    """{n, mae} of B1 on the rows where mask is true (mae None if the group is empty)."""
    part = frame[mask]
    if part.empty:
        return {"n": 0, "mae": None}
    return {"n": int(len(part)), "mae": r(metrics.mae(part["y"], baselines_a.b1_predict(part)))}


def breakdown(validation):
    """Descriptive only: B1's validation MAE by group. Nothing is tuned on it."""
    by_format = {str(fmt): group_mae(validation, validation["format"] == fmt)
                 for fmt in sorted(validation["format"].dropna().unique())}
    sequel = validation["is_sequel"].astype(bool)
    flags = {}
    for flag in FLAGS + ("any_of_three",):
        mask = validation[list(FLAGS)].astype(bool).any(axis=1) if flag == "any_of_three" else validation[flag].astype(bool)
        flags[flag] = {"flagged": group_mae(validation, mask), "unflagged": group_mae(validation, ~mask)}
    return {"b1_by_format": by_format, "b1_by_sequel": {"sequel": group_mae(validation, sequel),
                                                         "non_sequel": group_mae(validation, ~sequel)},
            "b1_by_flag": flags}


def build_report(train, validation, code_commit, data_fingerprint, fingerprint_splits, versions):
    predictions, fitted = baselines_a.run_baselines(train, validation)
    y_val = validation["y"].to_numpy(dtype=float)
    table = {}
    for name, by_split in predictions.items():
        on_validation = scores(y_val, by_split["validation"])
        low, high = metrics.bootstrap_ci(metrics.mae, y_val, by_split["validation"], n=1000, seed=42)
        on_validation["mae_ci95"] = [r(low), r(high)]
        table[name] = {"train": scores(train["y"].to_numpy(dtype=float), by_split["train"]), "validation": on_validation}
    return {
        "code_commit": code_commit, "data_fingerprint": data_fingerprint, "data_fingerprint_splits": sorted(fingerprint_splits),
        "library_versions": dict(sorted(versions.items())),
        "rows": {"train": int(len(train)), "validation": int(len(validation))},
        "test_split": "not loaded",
        "bootstrap": {"resamples": 1000, "seed": 42, "level": 95},
        "baselines": table,
        "fitted": {"b2_train_mean": r(fitted["train_mean"]), "b3_coefficient": r(fitted["coefficient"]),
                   "b3_intercept": r(fitted["intercept"])},
        "validation_breakdown": breakdown(validation),
    }


def render(report):
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def table_lines(report):
    """The printable baseline table."""
    lines = [f"{'baseline':<9}{'split':<12}{'MAE':>8}{'  MAE 95% CI':>18}{'RMSE':>9}{'within +-3':>12}"]
    names = {"B1": "B1 finale = ep3", "B2": "B2 train mean", "B3": "B3 linear"}
    for name, by_split in report["baselines"].items():
        for split in ("train", "validation"):
            s = by_split[split]
            ci = f"[{s['mae_ci95'][0]:.2f}, {s['mae_ci95'][1]:.2f}]" if "mae_ci95" in s else ""
            lines.append(f"{names[name]:<17}{split:<12}{s['mae']:>8.2f}{ci:>18}{s['rmse']:>9.2f}{s['within_3']:>11.1f}%")
    return lines
