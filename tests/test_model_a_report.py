"""Offline tests for the funnel report and the K = 6 diagnosis."""
from episode_three.features import model_a, model_a_report
from tests.test_model_a_features import day, snap
from tests.test_model_a_ledger import candidate_doc, w1_for, w2_for


def build():
    cands = [candidate_doc(1), candidate_doc(2, season_year=2024), candidate_doc(3, season_year=2025),
             candidate_doc(4, w1_status="no_records"), candidate_doc(5, eligible=False, exclusion_reasons=["duration_short"])]
    w1 = {"anilist:1": w1_for(), "anilist:2": w1_for(), "anilist:3": w1_for(100)}
    w2 = {"anilist:1": w2_for(60), "anilist:2": w2_for(70), "anilist:3": w2_for(80)}
    return cands, model_a.build_all(cands, w1, w2)


def test_funnel_adds_up_and_is_deterministic():
    cands, docs = build()
    text = model_a_report.funnel_markdown(cands, docs)
    assert text == model_a_report.funnel_markdown(cands, docs)            # same input, same text: no timestamps
    assert "Listed by AniList" in text and "**5**" in text and "**Eligible: 4**" in text
    assert "**Trainable: 2** of 4 eligible." in text
    assert "| train | 1 |" in text and "| validation | 1 |" in text and "| test | 0 |" in text
    assert "| ep3_popularity_low | 1 |" in text and "| no_w1_records | 1 |" in text
    assert "correlation" in text   # the note that none are shown, and no table of them
    assert "r =" not in text


def test_label_stats():
    assert model_a_report.label_stats([]) == ("0", "-", "-")
    assert model_a_report.label_stats([60, 70, 80]) == ("3", "70.00", "10.00")


def test_diagnosis_reports_only_what_a_wider_window_would_rescue():
    cands = [candidate_doc(1)]
    # ep3 window for K = 3 is Jan 21-23; the only scored record is Jan 19: found with K = 6, not with K = 3
    w1 = {"anilist:1": [snap(day(1, 9), 70, popularity=2000), snap(day(1, 19), 75, popularity=3000)]}
    docs = model_a.build_all(cands, w1, {"anilist:1": w2_for()})
    assert docs[0]["reasons"] == ["no_ep3_snapshot"]
    result = model_a_report.diagnose_k(docs, w1, k=6)
    assert result["missing"] == 1 and result["rescued"] == [("anilist:1", 3000)] and result["passing"] == result["rescued"]
    assert model_a_report.diagnose_k(docs, w1, k=3)["rescued"] == []
    assert docs[0]["status"] == "excluded"          # the diagnosis changed nothing
    low = {"anilist:1": [snap(day(1, 19), 75, popularity=1500)]}
    assert model_a_report.diagnose_k(docs, low, k=6)["passing"] == []
