"""Choose the Model A family on validation. Pure given its inputs (no database, no clock), deterministic.

Steps: tune every family x popularity variant by time CV inside train; keep the best variant per family (by CV);
refit that configuration on train; score on validation once, with paired bootstrap CIs against B1 and B3; name the
family with the lowest validation MAE; permutation importance for that family only.
"""
import numpy as np
from sklearn.inspection import permutation_importance

from episode_three.models import baselines_a, features_a, metrics, train_a
from episode_three.models.report_a import ROUND, r


def validation_scores(truth, prediction, baselines):
    """MAE [CI], RMSE, within +-3, and the paired difference versus each baseline's errors (model - baseline)."""
    error = np.abs(truth - prediction)
    low, high = metrics.bootstrap_ci(metrics.mae, truth, prediction, n=1000, seed=42)
    row = {"mae": r(metrics.mae(truth, prediction)), "mae_ci95": [r(low), r(high)],
           "rmse": r(metrics.rmse(truth, prediction)), "within_3": r(metrics.pct_within(truth, prediction, 3))}
    for name, base_prediction in baselines.items():
        base_error = np.abs(truth - base_prediction)
        low, high = metrics.paired_bootstrap_ci(error, base_error, n=1000, seed=42)
        row[f"diff_vs_{name.lower()}"] = {"mean": r(np.mean(error - base_error)), "ci95": [r(low), r(high)],
                                            "better": bool(high < 0)}
    return row


def importance_table(model, X, y_delta, base, top=10):
    """Permutation importance on validation: how much the finale MAE grows when one input column is shuffled.

    The base (ep3 score) used to turn a delta back into a finale is held fixed, so shuffling the ep3_score
    COLUMN only removes what the model learns from it.
    """
    truth = base + np.asarray(y_delta, dtype=float)

    def scorer(estimator, X_permuted, _y):
        return -float(np.mean(np.abs(truth - np.clip(base + estimator.predict(X_permuted), 0, 100))))

    result = permutation_importance(model, X, y_delta, scoring=scorer, n_repeats=20, random_state=42, n_jobs=1)
    order = sorted(range(len(X.columns)), key=lambda i: (-result.importances_mean[i], X.columns[i]))[:top]
    return [{"feature": X.columns[i], "mae_increase": r(result.importances_mean[i]), "std": r(result.importances_std[i])}
            for i in order]


def run_selection(train, validation, code_commit, data_fingerprint, fingerprint_splits, versions, progress=None):
    """Returns (report dict, {"models": fitted pipelines per family, "chosen": family})."""
    cv, chosen_variant = [], {}
    for family in train_a.FAMILIES:
        for variant in features_a.POPULARITY_VARIANTS:
            result = train_a.tune_family(family, train, variant)
            cv.append(result)
            if progress:
                progress(result)
        best = min((c for c in cv if c["family"] == family), key=lambda c: c["best_cv_mae"])   # ties: first variant
        chosen_variant[family] = best

    predictions, fitted = baselines_a.run_baselines(train, validation)
    X_val, y_delta_val, y_val = features_a.build_xy(validation, "raw")
    truth = y_val.to_numpy(dtype=float)
    base = X_val["ep3_score"].to_numpy(dtype=float)
    baseline_predictions = {"B1": predictions["B1"]["validation"], "B3": predictions["B3"]["validation"]}

    models, rows = {}, {"B1": validation_scores(truth, baseline_predictions["B1"], {"B3": baseline_predictions["B3"]}),
                        "B3": validation_scores(truth, baseline_predictions["B3"], {"B1": baseline_predictions["B1"]})}
    for family in train_a.FAMILIES:
        pick = chosen_variant[family]
        models[family] = train_a.fit_family(family, pick["best_params"], pick["variant"], train)
        X_family, _, _ = features_a.build_xy(validation, pick["variant"])
        prediction = train_a.predict_finale(models[family], X_family)
        rows[family] = validation_scores(truth, prediction, baseline_predictions)

    chosen = min(train_a.FAMILIES, key=lambda f: (rows[f]["mae"], train_a.FAMILIES.index(f)))
    pick = chosen_variant[chosen]
    X_chosen, y_delta_chosen, _ = features_a.build_xy(validation, pick["variant"])
    importance = importance_table(models[chosen], X_chosen, y_delta_chosen, base)
    beats_b1 = rows[chosen]["diff_vs_b1"]["better"]

    configurations = sum(train_a.n_configurations(f) for f in train_a.FAMILIES) * len(features_a.POPULARITY_VARIANTS)
    report = {
        "code_commit": code_commit, "data_fingerprint": data_fingerprint, "data_fingerprint_splits": sorted(fingerprint_splits),
        "library_versions": dict(sorted(versions.items())), "seed": train_a.SEED, "test_split": "not loaded",
        "rows": {"train": int(len(train)), "validation": int(len(validation))},
        "target": "delta = finale - ep3_score; prediction = clip(ep3_score + delta, 0, 100)",
        "cv_folds": [{"fit_up_to": y - 1, "score": y} for y in train_a.FOLD_TEST_YEARS],
        "grids": {f: train_a.GRIDS[f] for f in train_a.FAMILIES}, "rf_trees": train_a.RF_TREES,
        "popularity_variants": features_a.POPULARITY_VARIANTS,
        "cv": [{"family": c["family"], "variant": c["variant"], "best_params": c["best_params"],
                "best_cv_mae": r(c["best_cv_mae"]), "best_per_fold": [r(v) for v in c["per_fold"]],
                "all_configurations": [{"params": x["params"], "mean_cv_mae": r(x["mean_cv_mae"]),
                                        "per_fold": [r(v) for v in x["per_fold"]]} for x in c["results"]]} for c in cv],
        "chosen_per_family": {f: {"variant": chosen_variant[f]["variant"], "params": chosen_variant[f]["best_params"],
                                  "cv_mae": r(chosen_variant[f]["best_cv_mae"])} for f in train_a.FAMILIES},
        "validation": rows, "chosen_family": chosen, "chosen_beats_b1": bool(beats_b1),
        "chosen_beats_b3": bool(rows[chosen]["diff_vs_b3"]["better"]),
        "permutation_importance": {"family": chosen, "scoring": "finale MAE increase", "n_repeats": 20, "top10": importance},
        "counts": {"configurations_per_variant": {f: train_a.n_configurations(f) for f in train_a.FAMILIES},
                   "configurations": configurations, "cv_fits": configurations * len(train_a.FOLD_TEST_YEARS),
                   "refits": len(train_a.FAMILIES)},
    }
    return report, {"models": models, "chosen": chosen, "variants": {f: chosen_variant[f]["variant"] for f in train_a.FAMILIES}}


def selection_lines(report):
    """Printable CV table, chosen params, validation table and the verdict."""
    lines = ["Time-CV MAE on the finale score (mean over 4 folds, then per fold 2020 / 2021 / 2022 / 2023):",
             f"  {'family':<7}{'popularity':<12}{'CV MAE':>8}   per fold                 best params"]
    for c in report["cv"]:
        folds = " ".join(f"{v:5.2f}" for v in c["best_per_fold"])
        params = ", ".join(f"{k.split('__')[1]}={v}" for k, v in c["best_params"].items())
        lines.append(f"  {c['family']:<7}{c['variant']:<12}{c['best_cv_mae']:>8.3f}   {folds}   {params}")
    lines += ["", "Chosen per family (by CV):"]
    for family, pick in report["chosen_per_family"].items():
        params = ", ".join(f"{k.split('__')[1]}={x}" for k, x in pick["params"].items())
        lines.append(f"  {family}: popularity {pick['variant']}, {params} (CV MAE {pick['cv_mae']:.3f})")
    lines += ["", "Validation (192 shows), MAE with bootstrap 95% CI; difference = model error - baseline error, paired:",
              f"  {'model':<8}{'MAE':>6} {'MAE 95% CI':<16}{'RMSE':>6}{'+-3':>7}   {'vs B1 [95% CI]':<26}{'vs B3 [95% CI]':<26}"]
    for name in ("B1", "B3") + train_a.FAMILIES:
        row = report["validation"][name]
        cells = []
        for other in ("b1", "b3"):
            d = row.get(f"diff_vs_{other}")
            cells.append(f"{d['mean']:+.3f} [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}]" if d else "-")
        lines.append(f"  {name:<8}{row['mae']:>6.2f} [{row['mae_ci95'][0]:.2f}, {row['mae_ci95'][1]:.2f}]  "
                     f"{row['rmse']:>6.2f}{row['within_3']:>6.1f}%   {cells[0]:<26}{cells[1]:<26}")
    chosen = report["chosen_family"]
    verdict = ("BEATS B1: the paired 95% CI lies entirely below 0." if report["chosen_beats_b1"]
               else "does NOT beat B1 on validation: the paired 95% CI of (model - B1) includes 0 or lies above it.")
    lines += ["", f"Chosen family (lowest validation MAE): {chosen}; it {verdict}",
              f"Versus B3, the chosen family {'is' if report['chosen_beats_b3'] else 'is not'} better beyond noise.",
              "", f"Permutation importance of {chosen} on validation (finale MAE increase when the column is shuffled; descriptive only):"]
    lines += [f"  {i + 1:>2}. {t['feature']:<24}{t['mae_increase']:>+8.4f}  (+-{t['std']:.4f})"
              for i, t in enumerate(report["permutation_importance"]["top10"])]
    c = report["counts"]
    lines += ["", f"Configurations fitted: {c['configurations']} ({c['cv_fits']} CV fits + {c['refits']} refits on train)."]
    return lines


# --- TASK 014 ruling a: the Ridge alpha boundary extension (before the test lock) --------------------------------

EXTENDED_ALPHAS = (0.1, 1, 10, 100, 300, 1000, 3000)


def extend_ridge_alpha(train, validation, code_commit, alphas=EXTENDED_ALPHAS, variant="raw"):
    """Ridge-only time CV over a wider alpha grid (popularity fixed), then validation re-reported for the CV-best alpha.

    The family and the popularity variant are NOT reopened whatever validation shows; only alpha is chosen, by CV.
    """
    result = train_a.tune_family("ridge", train, variant, grid={"model__alpha": list(alphas)})
    chosen = result["best_params"]["model__alpha"]
    X_val, _, y_val = features_a.build_xy(validation, variant)
    truth = y_val.to_numpy(dtype=float)
    predictions, _ = baselines_a.run_baselines(train, validation)
    baselines = {"B1": predictions["B1"]["validation"], "B3": predictions["B3"]["validation"]}

    def validation_row(alpha):
        model = train_a.fit_family("ridge", {"model__alpha": alpha}, variant, train)
        return validation_scores(truth, train_a.predict_finale(model, X_val), baselines)

    return {
        "code_commit": code_commit, "popularity_variant": variant, "alphas": list(alphas),
        "cv": [{"alpha": x["params"]["model__alpha"], "mean_cv_mae": r(x["mean_cv_mae"]),
                "per_fold": [r(v) for v in x["per_fold"]]} for x in result["results"]],
        "chosen_alpha": chosen, "chosen_cv_mae": r(result["best_cv_mae"]),
        "chosen_at_boundary": chosen in (min(alphas), max(alphas)),
        "validation_at_chosen_alpha": validation_row(chosen),
        "validation_at_alpha_100": validation_row(100),
        "test_split": "not loaded",
    }


def extension_lines(extension):
    lines = [f"Ridge alpha extension (time CV inside train, popularity {extension['popularity_variant']}):",
             f"  {'alpha':>7}  {'CV MAE':>7}   per fold 2020 / 2021 / 2022 / 2023"]
    for row in extension["cv"]:
        mark = "  <- CV-best" if row["alpha"] == extension["chosen_alpha"] else ""
        lines.append(f"  {row['alpha']:>7}  {row['mean_cv_mae']:>7.3f}   " + " ".join(f"{v:5.2f}" for v in row["per_fold"]) + mark)
    where = (f"boundary: {extension['chosen_alpha']}" if extension["chosen_at_boundary"]
             else f"interior: {extension['chosen_alpha']}")
    lines += ["", f"Chosen alpha ({where}), CV MAE {extension['chosen_cv_mae']:.3f}.", "",
              "Validation, re-reported (192 shows; paired difference = Ridge error - baseline error):"]
    for label, key in (("alpha " + str(extension["chosen_alpha"]), "validation_at_chosen_alpha"), ("alpha 100 (TASK 013)", "validation_at_alpha_100")):
        row = extension[key]
        d1, d3 = row["diff_vs_b1"], row["diff_vs_b3"]
        lines.append(f"  {label:<22} MAE {row['mae']:.2f} [{row['mae_ci95'][0]:.2f}, {row['mae_ci95'][1]:.2f}]  RMSE {row['rmse']:.2f}  "
                     f"within +-3 {row['within_3']:.1f}%  vs B1 {d1['mean']:+.3f} [{d1['ci95'][0]:+.3f}, {d1['ci95'][1]:+.3f}]  "
                     f"vs B3 {d3['mean']:+.3f} [{d3['ci95'][0]:+.3f}, {d3['ci95'][1]:+.3f}]")
    return lines
