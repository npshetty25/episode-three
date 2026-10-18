"""Offline tests for the baselines and the report."""
import inspect
import json

import numpy as np
import pandas as pd
import pytest

from episode_three.models import baselines_a, report_a

FLAGS = {"marker_disagreement": False, "label_offset_unusual": False, "m1_unknown": False}


def frame(rows):
    """rows: (ep3_score, y) or (ep3_score, y, extras dict)."""
    data = []
    for i, row in enumerate(rows):
        extras = row[2] if len(row) > 2 else {}
        data.append({"_id": f"anilist:{i}", "ep3_score": row[0], "y": row[1], "format": "TV", "is_sequel": False,
                     **FLAGS, **extras})
    return pd.DataFrame(data)


TRAIN = frame([(60, 62), (70, 72), (80, 82), (90, 92)])        # y = ep3 + 2 exactly; mean y = 77
VALIDATION = frame([(65, 70), (75, 74), (85, 90), (95, 99)])


def test_b1_is_the_ep3_score():
    assert list(baselines_a.b1_predict(VALIDATION)) == [65, 75, 85, 95]


def test_b2_uses_the_train_mean_only():
    assert baselines_a.b2_fit(TRAIN) == 77.0
    assert list(inspect.signature(baselines_a.b2_fit).parameters) == ["train_frame"]   # it cannot even see another frame
    changed = VALIDATION.assign(y=[1, 2, 3, 4])                  # different validation labels ...
    predictions, fitted = baselines_a.run_baselines(TRAIN, changed)
    assert fitted["train_mean"] == 77.0 and list(predictions["B2"]["validation"]) == [77.0] * 4   # ... same B2
    assert list(predictions["B2"]["train"]) == [77.0] * 4


def test_b3_is_fitted_on_train_only():
    predictions, fitted = baselines_a.run_baselines(TRAIN, VALIDATION)
    assert fitted["coefficient"] == pytest.approx(1.0) and fitted["intercept"] == pytest.approx(2.0)
    assert list(predictions["B3"]["validation"]) == pytest.approx([67, 77, 87, 97])
    other_validation = VALIDATION.assign(y=[0, 0, 0, 0])         # validation labels never reach the fit
    assert baselines_a.run_baselines(TRAIN, other_validation)[1] == fitted


def versions():
    return {"python": "3.13.0", "numpy": "2.5.3"}


def build(commit="a" * 40):
    return report_a.build_report(TRAIN, VALIDATION, commit, "f" * 64, ("train", "validation"), versions())


def test_report_is_byte_identical_for_the_same_code_and_data():
    first, second = report_a.render(build()), report_a.render(build())
    assert first == second and first.endswith("\n")
    parsed = json.loads(first)
    assert parsed["code_commit"] == "a" * 40 and parsed["test_split"] == "not loaded"
    assert not any(word in first.lower() for word in ("timestamp", "generated_at", "created", "date"))
    assert build("b" * 40) != build("a" * 40)                    # a different commit changes the file


def test_report_contents():
    report = build()
    b1 = report["baselines"]["B1"]["validation"]
    assert b1["mae"] == pytest.approx(3.75)                       # misses 5, 1, 5, 4
    assert b1["within_3"] == 25.0 and len(b1["mae_ci95"]) == 2 and b1["mae_ci95"][0] <= b1["mae"] <= b1["mae_ci95"][1]
    assert report["baselines"]["B3"]["train"]["mae"] == 0.0
    assert report["fitted"]["b3_coefficient"] == 1.0 and report["fitted"]["b2_train_mean"] == 77.0
    assert report["rows"] == {"train": 4, "validation": 4} and report["bootstrap"]["seed"] == 42


def test_breakdown_splits_by_format_sequel_and_flags():
    validation = frame([(65, 70, {"format": "TV"}), (75, 74, {"format": "ONA", "is_sequel": True}),
                        (85, 90, {"marker_disagreement": True}), (95, 99, {"m1_unknown": True})])
    b = report_a.breakdown(validation)
    assert b["b1_by_format"]["TV"] == {"n": 3, "mae": round((5 + 5 + 4) / 3, 4)} and b["b1_by_format"]["ONA"] == {"n": 1, "mae": 1.0}
    assert b["b1_by_sequel"]["sequel"]["n"] == 1 and b["b1_by_sequel"]["non_sequel"]["n"] == 3
    md = b["b1_by_flag"]["marker_disagreement"]
    assert md["flagged"] == {"n": 1, "mae": 5.0} and md["unflagged"]["n"] == 3
    assert b["b1_by_flag"]["any_of_three"]["flagged"]["n"] == 2
    assert b["b1_by_flag"]["label_offset_unusual"]["flagged"] == {"n": 0, "mae": None}


def test_table_lines_print_every_baseline_on_both_splits():
    lines = report_a.table_lines(build())
    assert len(lines) == 1 + 3 * 2 and "B3 linear" in lines[-1] and np.isfinite(float(lines[1].split()[-3]))
