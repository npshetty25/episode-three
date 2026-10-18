"""Offline tests for the Model A prequel/popularity features, the split, leakage and the exclusion ledger."""
import inspect

from episode_three.features import model_a as ma
from tests.test_model_a_features import day, snap


def prequel(pid, fmt="TV", media="ANIME", kind="PREQUEL"):
    return {"type": kind, "id": pid, "media_type": media, "format": fmt}


def test_prequel_score_needs_a_final_prequel_before_the_ep3_snapshot():
    ep3_date = day(5, 1)
    finales = {"anilist:1": (80, day(3, 1)), "anilist:2": (70, day(5, 1)), "anilist:3": (60, day(6, 1))}
    ok = ma.prequel_features([prequel("anilist:1")], finales, ep3_date)
    assert (ok["is_sequel"], ok["prequel_finale_score"], ok["prequel_score_known"]) == (True, 80, True)
    # finished the same day as our ep3 snapshot, or after it: not final yet -> dropped by the date rule
    for pid in ("anilist:2", "anilist:3"):
        late = ma.prequel_features([prequel(pid)], finales, ep3_date)
        assert late["is_sequel"] and late["prequel_finale_score"] is None and not late["prequel_score_known"]
        assert late["prequel_dropped_by_date"] == [pid]
    outside = ma.prequel_features([prequel("anilist:99")], finales, ep3_date)  # a prequel we hold no label for
    assert outside["is_sequel"] and outside["prequel_finale_score"] is None and outside["prequel_dropped_by_date"] == []
    both = ma.prequel_features([prequel("anilist:1"), prequel("anilist:3")], finales, ep3_date)
    assert both["prequel_finale_score"] == 80 and both["prequel_dropped_by_date"] == ["anilist:3"]


def test_sequel_flag_counts_only_anime_prequels_of_the_right_format():
    for fmt in ("OVA", "SPECIAL"):
        assert ma.prequel_features([prequel("a", fmt)], {}, None)["is_sequel"] is False
    assert ma.prequel_features([prequel("a", "NOVEL", "MANGA")], {}, None)["is_sequel"] is False
    assert ma.prequel_features([prequel("a", "TV", kind="SEQUEL")], {}, None)["is_sequel"] is False
    for fmt in ("TV", "ONA", "TV_SHORT", "MOVIE"):
        assert ma.prequel_features([prequel("a", fmt)], {}, None)["is_sequel"] is True
    assert ma.prequel_features(None, {}, None)["is_sequel"] is False


def test_popularity_normalisations():
    peers = [1000, 2000, 3000, 4000]
    assert ma.popularity_season_pct(1000, peers) == 12.5     # (0 below + 0.5 * 1 equal) / 4
    assert ma.popularity_season_pct(4000, peers) == 87.5
    assert ma.popularity_season_pct(3000, [3000, 3000]) == 50.0   # ties share the middle
    assert ma.popularity_season_pct(None, peers) is None and ma.popularity_season_pct(5, []) is None
    assert ma.popularity_vs_previous(6000, [2000, 4000, 12000]) == 1.5     # the median is 4000
    assert ma.popularity_vs_previous(6000, []) is None
    assert ma.previous_season(2019, "WINTER") == (2018, "FALL")
    assert ma.previous_season(2019, "SUMMER") == (2019, "SPRING")


def test_split_assignment_and_disjointness():
    assert [ma.assign_split(y) for y in (2018, 2023, 2024, 2025, 2026)] == ["train", "train", "validation", "test", "test"]
    seasons = {"a": (2023, "FALL"), "b": (2024, "WINTER"), "c": (2025, "WINTER")}
    ma.assert_splits_disjoint({k: ma.assign_split(v[0]) for k, v in seasons.items()}, seasons)
    try:
        ma.assert_splits_disjoint({"a": "train", "b": "validation"}, {"a": (2024, "FALL"), "b": (2024, "WINTER")})
    except AssertionError:
        return
    raise AssertionError("an overlap in time must be caught")


# --- leakage: features see window 1 only -----------------------------------------------------------------

def test_feature_functions_never_receive_window_two_data():
    for fn in (ma.snapshot_result, ma.select_snapshot, ma.floor_impact, ma.score_features,
               ma.final_markers, ma.prequel_features):
        names = " ".join(inspect.signature(fn).parameters)
        assert "w2" not in names and "label" not in names, fn.__name__
        source = inspect.getsource(fn)
        assert "snapshots_w2" not in source and "primary_label" not in source, fn.__name__


def candidate_doc(number, season_year=2019, season="WINTER", **extra):
    schedule = {"ep1": day(1, 3), "ep2": day(1, 10), "ep3": day(1, 17), "ep4": day(1, 24), "final": day(3, 28)}
    doc = {"_id": f"anilist:{number}", "eligible": True, "season": season, "season_year": season_year,
           "episodes": 12, "w1_status": "collected", "relations": [],
           "start_date": {"year": 2019, "month": 1, "day": 3}, "end_date": {"year": 2019, "month": 3, "day": 28},
           "markers": {"schedule": schedule}, "marker_source": {"w1": "schedule", "w2": "schedule"},
           "trend_windows": {"w2": {"from": day(3, 27), "to": day(4, 7)}}}
    doc.update(extra)
    return doc


def w1_for(popularity=5000):
    return [snap(day(1, 9), 70, popularity=2000), snap(day(1, 23), 75, popularity=popularity)]


def w2_for(score=80):
    return [snap(day(3, 28), score, episode=12), snap(day(3, 29), score + 2, releasing=False)]


def test_changing_window_two_never_changes_the_features():
    cands = [candidate_doc(1)]
    base = ma.build_all(cands, {"anilist:1": w1_for()}, {"anilist:1": w2_for(80)})[0]
    other = ma.build_all(cands, {"anilist:1": w1_for()}, {"anilist:1": w2_for(55)})[0]
    assert base["features"] == other["features"] and base["ep3"] == other["ep3"]
    assert base["label"]["score"] == 80 and other["label"]["score"] == 55
    no_w2 = ma.build_all(cands, {"anilist:1": w1_for()}, {})[0]
    assert no_w2["features"] == base["features"] and no_w2["label"] is None


# --- the ledger ----------------------------------------------------------------------------------------

def test_every_eligible_show_gets_exactly_one_status_and_a_reason_if_excluded():
    cands = [candidate_doc(1), candidate_doc(2), candidate_doc(3, w1_status="no_records"),
             candidate_doc(4, eligible=False), candidate_doc(5), candidate_doc(6)]
    w1 = {"anilist:1": w1_for(), "anilist:2": w1_for(popularity=100), "anilist:5": [], "anilist:6": w1_for()}
    w2 = {"anilist:1": w2_for(), "anilist:2": w2_for(), "anilist:6": []}
    docs = ma.build_all(cands, w1, w2)
    by_id = {d["_id"]: d for d in docs}
    assert sorted(by_id) == ["anilist:1", "anilist:2", "anilist:3", "anilist:5", "anilist:6"]  # not the ineligible one
    assert len(docs) == len(by_id)
    for d in docs:
        assert d["status"] in ("trainable", "excluded") and (d["status"] == "trainable") == (d["reasons"] == [])
    assert by_id["anilist:1"]["status"] == "trainable"
    assert by_id["anilist:2"]["reasons"] == ["ep3_popularity_low"]
    assert by_id["anilist:3"]["reasons"][0] == "no_w1_records"
    assert by_id["anilist:5"]["reasons"] == ["no_ep3_snapshot", "no_primary_label"]
    assert by_id["anilist:5"]["subreasons"]["no_ep3_snapshot"] == "no_scored_record"
    assert by_id["anilist:6"]["reasons"] == ["no_primary_label"]


def test_ledger_reasons_for_marker_problems():
    def result(m3, m4, ep3=None, lost=False):
        markers = {n: {"day": None, "source": None} for n in (1, 2, 3, 4)}
        markers[3], markers[4] = {"day": m3, "source": "schedule"}, {"day": m4, "source": "schedule"}
        return {"markers": markers, "ep3": ep3, "ep3_reason": "no_scored_record", "floor": {"ep3": {"lost": lost}}}
    label = {"score": 1}
    assert ma.ledger("collected", result(None, None), False, label) == (["no_ep1_4_trends"], {"no_ep1_4_trends": "no_m3_m4"})
    assert ma.ledger("collected", result(day(1, 5), day(1, 5)), True, label)[1] == {"m3_not_before_m4": "binge"}
    assert ma.ledger("collected", result(None, None), True, label) == (["m3_not_before_m4"], {"m3_not_before_m4": "binge"})  # no markers at all
    assert ma.ledger("collected", result(day(1, 5), day(1, 5)), False, label)[1] == {"m3_not_before_m4": "same_day"}
    assert ma.ledger("collected", result(day(1, 6), day(1, 5)), False, label)[1] == {"m3_not_before_m4": "inverted"}
    assert ma.ledger("collected", result(day(1, 1), day(1, 3), lost=True), False, label)[1] == {"no_ep3_snapshot": "lost_to_floor"}
    assert ma.ledger("collected", result(day(1, 1), day(1, 8), ep3={"popularity": 5000}), False, label) == ([], {})


def test_ep1_features_are_null_but_the_show_is_kept_when_m1_is_unknown():
    doc = candidate_doc(1)
    doc["markers"]["schedule"]["ep1"] = None
    built = ma.build_all([doc], {"anilist:1": w1_for()}, {"anilist:1": w2_for()})[0]
    assert built["status"] == "trainable" and built["flags"]["m1_unknown"] is True
    assert built["features"]["ep1_score"] is None and built["features"]["score_delta_1_3"] is None
    assert built["features"]["popularity_growth_1_3"] is None and built["features"]["ep3_score"] == 75


def test_prequel_label_flows_through_build_all_and_the_date_rule_drops_late_ones():
    early = candidate_doc(1, season_year=2018, season="FALL",
                          trend_windows={"w2": {"from": day(12, 1, 2018), "to": day(12, 12, 2018)}})
    late = candidate_doc(2, relations=[prequel("anilist:3")])
    sequel = candidate_doc(3, relations=[prequel("anilist:1")])
    ids = ("anilist:1", "anilist:2", "anilist:3")
    docs = {d["_id"]: d for d in ma.build_all([early, late, sequel], {i: w1_for() for i in ids},
                                              {i: w2_for(70 + n) for n, i in enumerate(ids)})}
    # show 2's prequel (show 3) finishes in March 2019, after show 2's ep3 snapshot in January 2019: dropped
    assert docs["anilist:2"]["features"]["prequel_finale_score"] is None
    assert docs["anilist:2"]["prequel_dropped_by_date"] == ["anilist:3"]
    assert docs["anilist:3"]["features"]["prequel_finale_score"] == 70   # show 1 finished in December 2018


def test_popularity_normalisations_use_the_same_and_the_previous_season_only():
    cands = [candidate_doc(n, season_year=2019, season="SPRING") for n in (1, 2)] + \
            [candidate_doc(3, season_year=2019, season="WINTER")]
    w1 = {"anilist:1": w1_for(3000), "anilist:2": w1_for(9000), "anilist:3": w1_for(6000)}
    docs = {d["_id"]: d for d in ma.build_all(cands, w1, {})}
    assert docs["anilist:3"]["features"]["ep3_popularity_vs_prev_season"] is None      # nothing before Winter 2019
    assert docs["anilist:1"]["features"]["ep3_popularity_vs_prev_season"] == 0.5        # 3000 / 6000 (Winter 2019)
    assert docs["anilist:2"]["features"]["ep3_popularity_season_pct"] == 75.0           # above 1 of 2 same-season peers
