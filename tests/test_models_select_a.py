"""Offline tests for episode_three/models/select_a.py (tiny grids and forests so they run in seconds)."""
import json

import numpy as np
import pytest

from episode_three.models import select_a, train_a
from tests.test_models_train_a import make_df


@pytest.fixture
def tiny(monkeypatch):
    monkeypatch.setattr(train_a, "GRIDS", {"ridge": {"model__alpha": [1, 10]}, "rf": {"model__min_samples_leaf": [5]},
                                           "hgb": {"model__max_iter": [20]}})
    monkeypatch.setattr(train_a, "RF_TREES", 20)


def run(commit="c" * 40):
    train = make_df()
    validation = make_df(years=(2024,), per_year=30, split="validation", seed=5)
    return select_a.run_selection(train, validation, commit, "f" * 64, ("train", "validation"), {"python": "3.13"})


def test_selection_report_is_deterministic_and_complete(tiny):
    first, fitted = run()
    second, _ = run()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)     # same code + data -> same bytes
    assert first["test_split"] == "not loaded" and first["code_commit"] == "c" * 40
    assert set(first["validation"]) == {"B1", "B3", "ridge", "rf", "hgb"}
    assert first["chosen_family"] == fitted["chosen"] == min(train_a.FAMILIES, key=lambda f: first["validation"][f]["mae"])
    assert len(first["cv"]) == 3 * 3                                  # 3 families x 3 popularity variants
    assert len(first["permutation_importance"]["top10"]) == 10
    assert first["counts"]["configurations"] == (2 + 1 + 1) * 3 and first["counts"]["cv_fits"] == 4 * first["counts"]["configurations"]


def test_paired_differences_are_consistent_with_the_maes(tiny):
    report, _ = run()
    b1 = report["validation"]["B1"]["mae"]
    for family in train_a.FAMILIES:
        row = report["validation"][family]
        assert row["diff_vs_b1"]["mean"] == pytest.approx(row["mae"] - b1, abs=2e-4)     # mean paired diff = MAE diff
        low, high = row["diff_vs_b1"]["ci95"]
        assert low <= row["diff_vs_b1"]["mean"] <= high and row["diff_vs_b1"]["better"] == (high < 0)
    assert "diff_vs_b1" not in report["validation"]["B1"]


def test_validation_rows_do_not_influence_the_tuning_or_the_cv_numbers(tiny):
    train = make_df()
    changed = make_df(years=(2024,), per_year=30, split="validation", seed=99)
    other = make_df(years=(2024,), per_year=30, split="validation", seed=5)
    a, _ = select_a.run_selection(train, changed, "c" * 40, "f", ("train",), {})
    b, _ = select_a.run_selection(train, other, "c" * 40, "f", ("train",), {})
    assert a["cv"] == b["cv"] and a["chosen_per_family"] == b["chosen_per_family"]     # different validation, same search
    assert a["validation"] != b["validation"]


def test_printable_lines_name_the_chosen_family(tiny):
    report, _ = run()
    text = "\n".join(select_a.selection_lines(report))
    assert f"Chosen family (lowest validation MAE): {report['chosen_family']}" in text
    assert "Permutation importance" in text and "Configurations fitted: 12" in text
    assert np.isfinite(report["validation"]["ridge"]["mae"])


# --- TASK 014 ruling a: the alpha extension ---------------------------------------------------------------------

def test_alpha_extension_chooses_by_cv_and_never_touches_validation_for_the_choice():
    train = make_df()
    one = make_df(years=(2024,), per_year=30, split="validation", seed=5)
    two = make_df(years=(2024,), per_year=30, split="validation", seed=99)
    a = select_a.extend_ridge_alpha(train, one, "c" * 40)
    b = select_a.extend_ridge_alpha(train, two, "c" * 40)
    assert [row["alpha"] for row in a["cv"]] == list(select_a.EXTENDED_ALPHAS)
    assert a["chosen_alpha"] == b["chosen_alpha"] and a["cv"] == b["cv"]          # chosen on train CV only
    assert a["chosen_cv_mae"] == min(row["mean_cv_mae"] for row in a["cv"])
    assert a["chosen_at_boundary"] == (a["chosen_alpha"] in (0.1, 3000))
    assert a["validation_at_chosen_alpha"] != b["validation_at_chosen_alpha"]      # validation is only re-reported
    assert a["test_split"] == "not loaded" and a["popularity_variant"] == "raw"
    assert "diff_vs_b1" in a["validation_at_chosen_alpha"] and "diff_vs_b3" in a["validation_at_alpha_100"]
    text = "\n".join(select_a.extension_lines(a))
    assert "CV-best" in text and "Chosen alpha (" in text
    assert json.dumps(a, sort_keys=True) == json.dumps(select_a.extend_ridge_alpha(train, one, "c" * 40), sort_keys=True)
