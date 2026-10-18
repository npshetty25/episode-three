"""Offline tests for the Model A final evaluation: lock, run-once guard, refit, scoring, determinism."""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from episode_three.models import final_a, features_a, select_a
from tests.test_models_train_a import make_df

ROOT = Path(__file__).resolve().parent.parent
LOCK = {"family": "ridge", "alpha": 100, "popularity_variant": "raw", "features": features_a.INPUT_COLUMNS,
        "target": "delta", "trainval_data_fingerprint": "f" * 64, "planned_report_sections": list(final_a.PLANNED_SECTIONS),
        "final_fit": {"rows": {"train": 681, "validation": 192, "total": 873}}}


def eval_frame(n=40, seed=3):
    """A test-like frame with every column the evaluation reads."""
    df = make_df(years=(2025,), per_year=n, split="test", seed=seed)
    rng = np.random.default_rng(seed)
    df["title_romaji"] = [f"Show {i}" for i in range(len(df))]
    df["y_secondary"] = [None if i % 4 == 0 else v + 1 for i, v in enumerate(df["y"])]
    for flag in ("marker_disagreement", "label_offset_unusual", "m1_unknown", "fallback_w1", "fallback_w2"):
        df[flag] = rng.random(len(df)) < 0.1
    return df


def fitted_for(fit_frame):
    return final_a.refit(fit_frame, LOCK)


# --- the lock ------------------------------------------------------------------------------------------------

def fake_git(tracked=True, changes=""):
    def git(*args):
        if args[0] == "ls-files":
            return (0 if tracked else 1), ""
        return 0, changes
    return git


def test_lock_missing_uncommitted_or_modified_is_refused(tmp_path):
    path = tmp_path / "lock.json"
    with pytest.raises(final_a.LockError, match="does not exist"):
        final_a.check_lock(path, git=fake_git())
    path.write_text(json.dumps(LOCK), encoding="utf-8")
    with pytest.raises(final_a.LockError, match="not committed"):
        final_a.check_lock(path, git=fake_git(tracked=False))
    with pytest.raises(final_a.LockError, match="uncommitted changes"):
        final_a.check_lock(path, git=fake_git(changes=" M reports/model_a_test_lock.json"))
    assert final_a.check_lock(path, git=fake_git())["alpha"] == 100


def test_build_lock_contains_the_plan_and_no_timestamps():
    selection = {"chosen_family": "ridge", "ridge_alpha_extension": {
        "chosen_alpha": 100, "popularity_variant": "raw", "alphas": [0.1, 1, 10, 100], "chosen_at_boundary": False}}
    lock = final_a.build_lock(selection, "a" * 64, {"train": 681, "validation": 192, "total": 873}, "c" * 40)
    assert (lock["family"], lock["alpha"], lock["popularity_variant"]) == ("ridge", 100, "raw")
    assert lock["features"] == features_a.INPUT_COLUMNS and lock["planned_report_sections"] == list(final_a.PLANNED_SECTIONS)
    assert lock["trainval_data_fingerprint"] == "a" * 64 and lock["code_commit"] == "c" * 40
    assert lock["test_split"].startswith("not loaded") and lock["final_fit"]["rows"]["total"] == 873
    assert "timestamp" not in json.dumps(lock).lower()
    with pytest.raises(final_a.LockError):
        final_a.build_lock(dict(selection, chosen_family="rf"), "a", {}, "c")


def test_lock_hash_ignores_line_endings(tmp_path):
    lf, crlf = tmp_path / "lf.json", tmp_path / "crlf.json"
    lf.write_bytes(b'{"a": 1}\n')
    crlf.write_bytes(b'{"a": 1}\r\n')
    assert final_a.lock_sha256(lf) == final_a.lock_sha256(crlf)


# --- the run-once guard ---------------------------------------------------------------------------------------

def test_run_once_guard(tmp_path):
    report = tmp_path / "model_a_v1.json"
    assert final_a.check_run_once(report, None) == (1, [])
    report.write_text(json.dumps({"run_count": 1, "rerun_reasons": []}), encoding="utf-8")
    with pytest.raises(final_a.AlreadyEvaluated, match="already evaluated"):
        final_a.check_run_once(report, None)
    assert final_a.check_run_once(report, "fixed a typo in the table") == (2, ["fixed a typo in the table"])
    report.write_text(json.dumps({"run_count": 2, "rerun_reasons": ["first"]}), encoding="utf-8")
    assert final_a.check_run_once(report, "second") == (3, ["first", "second"])


def test_script_main_raises_already_evaluated_without_a_reason(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT))
    from scripts import evaluate_model_a_final as script
    existing = tmp_path / "model_a_v1.json"
    existing.write_text(json.dumps({"run_count": 1, "rerun_reasons": []}), encoding="utf-8")
    real_check = final_a.check_run_once
    monkeypatch.setattr(final_a, "check_lock", lambda *a, **k: LOCK)
    monkeypatch.setattr(final_a, "lock_sha256", lambda *a, **k: "0" * 64)
    monkeypatch.setattr(final_a, "check_run_once", lambda rerun_reason=None: real_check(existing, rerun_reason))
    monkeypatch.setattr(script.db, "get_client", lambda: (_ for _ in ()).throw(AssertionError("database touched")))
    monkeypatch.setattr(sys, "argv", ["evaluate_model_a_final"])
    with pytest.raises(final_a.AlreadyEvaluated, match="--rerun-reason"):
        script.main()


# --- only one place loads the test split -----------------------------------------------------------------------------

def test_the_test_split_is_requested_from_one_script_only():
    pattern = re.compile(r"allow_test\s*=\s*True")
    offenders = []
    for folder in ("episode_three", "scripts"):
        for path in (ROOT / folder).rglob("*.py"):
            if pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == ["scripts/evaluate_model_a_final.py"]
    assert len(pattern.findall((ROOT / "scripts" / "evaluate_model_a_final.py").read_text(encoding="utf-8"))) == 1


# --- refit and scoring -------------------------------------------------------------------------------------------------

def test_refit_uses_exactly_train_plus_validation_rows():
    train = make_df(years=(2018, 2019, 2020, 2021, 2022, 2023), per_year=114, split="train")[:681]
    validation = make_df(years=(2024,), per_year=192, split="validation", seed=8)
    both = pd.concat([train, validation], ignore_index=True)
    fitted = fitted_for(both)
    assert len(train) == 681 and len(validation) == 192 and fitted["n_fit"] == 873
    assert fitted["b2_mean"] == pytest.approx(both["y"].mean())          # B2 from all 873 labels, not just train
    assert fitted["b2_mean"] != pytest.approx(train["y"].mean())


def build(frame=None, fit=None):
    frame = eval_frame() if frame is None else frame
    fit = make_df() if fit is None else fit
    fitted = fitted_for(fit)
    results = final_a.evaluate(frame, final_a.predictions(fitted, frame))
    return frame, fitted, results


def test_evaluation_has_every_planned_section_and_the_secondary_label_skips_missing():
    frame, fitted, results = build()
    assert final_a.missing_sections(results) == []
    secondary = results["sensitivity"]["secondary_label"]
    assert secondary["n"] == int(frame["y_secondary"].notna().sum()) < len(frame)         # shows without it are skipped
    assert secondary["n"] + secondary["without_secondary_label"] == len(frame)
    has = frame["y_secondary"].notna().to_numpy()
    pred = final_a.predictions(fitted, frame)
    expected = float(np.mean(np.abs(frame["y_secondary"].to_numpy(dtype=float)[has] - pred["B1"][has])))
    assert secondary["b1_mae_vs_secondary"] == pytest.approx(expected, abs=1e-4)
    assert final_a.missing_sections({"primary": {}}) != []


def test_sensitivity_groups_partition_the_frame():
    frame, _, results = build()
    s = results["sensitivity"]
    assert sum(g["n"] for g in s["per_season"]) == len(frame)
    assert s["by_sequel"]["sequel"]["n"] + s["by_sequel"]["non_sequel"]["n"] == len(frame)
    assert sum(g["n"] for g in s["by_format"].values()) == len(frame)
    for name, group in s["excluding_flagged"].items():
        assert group["flagged"] + group["remaining"]["n"] == len(frame), name
    assert s["excluding_flagged"]["all_together"]["flagged"] >= max(g["flagged"] for g in s["excluding_flagged"].values())


def test_largest_errors_are_the_ten_biggest_in_order():
    frame, fitted, results = build()
    errors = [e["abs_error"] for e in results["largest_errors"]]
    assert len(errors) == 10 and errors == sorted(errors, reverse=True)
    pred = final_a.predictions(fitted, frame)
    all_errors = np.sort(np.abs(frame["y"].to_numpy(dtype=float) - pred["ridge"]))[::-1]
    assert errors[0] == pytest.approx(all_errors[0], abs=1e-4)
    assert {"id", "title", "season", "ep3_score", "prediction", "label"} <= set(results["largest_errors"][0])


def test_criterion_is_pass_only_at_least_ten_percent_below_b1():
    frame = eval_frame()
    truth = frame["y"].to_numpy(dtype=float)
    base = frame["ep3_score"].to_numpy(dtype=float)
    b1_mae = np.mean(np.abs(truth - base))
    for scale, expected in ((0.5, "PASS"), (0.9, "PASS"), (0.95, "FAIL"), (1.2, "FAIL")):
        pred = {"B1": base, "B2": base, "B3": base, "ridge": truth + (base - truth) * scale}   # ridge error = scale * B1 error
        result = final_a.evaluate(frame, pred)["criterion"]
        assert result["result"] == expected, scale
        assert result["reduction_pct"] == pytest.approx(100 * (1 - scale), abs=1e-3)
    assert b1_mae > 0


def test_report_is_deterministic_and_renders_the_results_row():
    frame, fitted, results = build()
    fit_info = {"rows": fitted["n_fit"], "seasons": "A to B", "b2_mean": fitted["b2_mean"],
                "b3_coefficient": fitted["b3_coefficient"], "b3_intercept": fitted["b3_intercept"]}
    eval_info = {"rows": len(frame), "seasons": final_a.season_span(frame), "fingerprint": "e" * 64}

    def make():
        return final_a.build_report(results, LOCK, "9" * 64, fit_info, eval_info, 1, [], "c" * 40, {"python": "3.13"})
    first, second = final_a.render_json(make()), final_a.render_json(make())
    assert first == second and first.endswith("\n")
    assert not any(word in first.lower() for word in ("timestamp", "generated_at", "created_at"))
    report = json.loads(first)
    assert report["run_count"] == 1 and report["rerun_reasons"] == [] and report["lock_sha256"] == "9" * 64
    assert report["test_data_fingerprint"] == "e" * 64 and report["trainval_data_fingerprint"] == "f" * 64
    md = final_a.render_md(make())
    assert "README results row" in md and report["criterion"]["result"] in md
    assert "\n".join(final_a.result_lines(make())).count("CRITERION") == 1
    rerun = final_a.build_report(results, LOCK, "9" * 64, fit_info, eval_info, 2, ["why"], "c" * 40, {})
    assert rerun["run_count"] == 2 and rerun["rerun_reasons"] == ["why"]
