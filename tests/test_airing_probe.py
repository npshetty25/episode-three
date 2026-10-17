"""Offline tests for episode_three/collect/airing_probe.py, using a saved real response."""
from episode_three.collect import airing_probe as probe
from tests.conftest import load_fixture


def candidate(number, popularity, eligible=True):
    return {"_id": f"anilist:{number}", "eligible": eligible, "current_popularity": popularity}


def test_parse_the_saved_response():
    fixture = load_fixture("airing_schedules_sample.json")
    rows = fixture["data"]["Page"]["airingSchedules"]
    summary = probe.summarize_show_schedule(rows, fixture["episodes"])
    assert summary["rows"] == 13 == fixture["episodes"] == summary["distinct_episodes"]
    assert summary["status"] == "complete" and summary["missing_episodes"] == []
    assert summary["has_eps_1_to_4"] is True and summary["has_final_episode"] is True
    assert summary["first_airing_jst"] == "2018-10-04 02:15"
    assert summary["last_airing_jst"] == "2018-12-27 02:15"


def test_gaps_and_missing_schedules():
    rows = [{"mediaId": 1, "episode": e, "airingAt": 1_600_000_000 + e * 604_800} for e in (1, 2, 4, 12)]
    gaps = probe.summarize_show_schedule(rows, 12)
    assert gaps["status"] == "gaps" and gaps["has_eps_1_to_4"] is False and gaps["has_final_episode"] is True
    assert gaps["missing_episodes"] == [3, 5, 6, 7, 8, 9, 10, 11]

    empty = probe.summarize_show_schedule([], 12)
    assert empty["status"] == "missing" and empty["rows"] == 0
    assert empty["first_airing_jst"] is None and empty["has_final_episode"] is False


def test_season_verdicts():
    complete = {"status": "complete", "has_eps_1_to_4": True, "has_final_episode": True}
    gaps = {"status": "gaps", "has_eps_1_to_4": False, "has_final_episode": True}
    missing = {"status": "missing", "has_eps_1_to_4": False, "has_final_episode": False}
    detail, verdict = probe.season_verdict([complete, complete])
    assert verdict == "complete" and "2 complete" in detail
    detail, verdict = probe.season_verdict([complete, gaps, missing])
    assert verdict == "gaps" and "1/3 have eps 1-4 AND the final episode" in detail
    assert probe.season_verdict([missing, missing])[1] == "missing"
    assert probe.season_verdict([])[1] == "none"


def test_pick_is_evenly_spaced_deterministic_and_skips_ineligible():
    docs = [candidate(n, popularity=1000 - n) for n in range(1, 101)] + [candidate(999, 5000, eligible=False)]
    picked = probe.pick_probe_shows(docs, 10)
    assert len(picked) == 10
    assert picked[0]["_id"] == "anilist:1" and picked[-1]["_id"] == "anilist:100"  # most and least popular
    assert "anilist:999" not in [d["_id"] for d in picked]
    assert picked == probe.pick_probe_shows(list(reversed(docs)), 10)  # same shows whatever the input order


def test_pick_with_few_candidates_returns_them_all():
    docs = [candidate(1, 10), candidate(2, 30), candidate(3, 20, eligible=False)]
    assert [d["_id"] for d in probe.pick_probe_shows(docs, 10)] == ["anilist:2", "anilist:1"]
    assert probe.pick_probe_shows([], 10) == []


def test_ids_and_grouping():
    assert probe.anilist_id({"_id": "anilist:154587"}) == 154587
    rows = [{"mediaId": 1, "episode": 1}, {"mediaId": 2, "episode": 1}, {"mediaId": 1, "episode": 2}]
    grouped = probe.group_rows_by_show(rows)
    assert [r["episode"] for r in grouped[1]] == [1, 2] and len(grouped[2]) == 1
    assert "mediaId_in" in probe.AIRING_QUERY and "notYetAired" not in probe.AIRING_QUERY
