"""Offline tests for episode_three/collect/model_a_candidates.py and the collector script."""
from datetime import datetime, timezone

import pytest

from episode_three.clients import anilist
from episode_three.collect import model_a_candidates as candidates
from scripts import collect_model_a_candidates as collector
from tests.conftest import load_fixture

LISTED = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def good_media(**changes):
    """A media dict that passes every eligibility rule, with optional overrides."""
    media = {"id": 1, "format": "TV", "countryOfOrigin": "JP", "isAdult": False, "episodes": 12,
             "duration": 24, "status": "FINISHED"}
    media.update(changes)
    return media


def test_season_range_is_32_seasons_from_fall_2018_to_summer_2026():
    seasons = list(candidates.season_range())
    assert len(seasons) == 32 == len(set(seasons))
    assert seasons[0] == ("FALL", 2018) and seasons[-1] == ("SUMMER", 2026)
    assert [s for s, y in seasons if y == 2019] == ["WINTER", "SPRING", "SUMMER", "FALL"]
    assert [s for s, y in seasons if y == 2026] == ["WINTER", "SPRING", "SUMMER"]
    assert sum(1 for s, y in seasons if y == 2018) == 1


def test_a_good_show_is_eligible_with_no_reasons():
    assert candidates.check_eligibility(good_media()) == (True, [])
    assert candidates.check_eligibility(good_media(format="ONA"))[0] is True


@pytest.mark.parametrize("changes, reason", [
    ({"format": "MOVIE"}, "format"),
    ({"countryOfOrigin": "CN"}, "country"),
    ({"isAdult": True}, "adult"),
    ({"episodes": None}, "episodes_unknown"),
    ({"episodes": 7}, "episodes_out_of_range"),
    ({"episodes": 31}, "episodes_out_of_range"),
    ({"duration": None}, "duration_unknown"),
    ({"duration": 9}, "duration_short"),
    ({"status": "RELEASING"}, "not_finished"),
    ({"status": None}, "not_finished"),
])
def test_each_reason_code(changes, reason):
    assert candidates.check_eligibility(good_media(**changes)) == (False, [reason])


def test_boundaries_are_inclusive():
    for episodes in (8, 30):
        assert candidates.check_eligibility(good_media(episodes=episodes))[0] is True
    assert candidates.check_eligibility(good_media(duration=10))[0] is True


def test_a_show_can_have_several_reasons_and_nulls_do_not_crash():
    eligible, reasons = candidates.check_eligibility({"id": 2})
    assert eligible is False
    assert reasons == ["format", "country", "episodes_unknown", "duration_unknown", "not_finished"]
    _, reasons = candidates.check_eligibility(good_media(episodes=3, duration=5, status="RELEASING", isAdult=True))
    assert reasons == ["adult", "episodes_out_of_range", "duration_short", "not_finished"]


def test_candidate_doc_from_fixture_has_prefixed_ids_and_current_fields():
    first, second = load_fixture("model_a_media_sample.json")["media"]
    doc = candidates.to_candidate_doc(first, LISTED)
    assert doc["_id"] == "anilist:5001" and doc["source"] == "anilist" and doc["mal_id"] == 9001
    assert doc["duration_min"] == 24 and doc["season_year"] == 2020 and doc["source_material"] == "MANGA"
    assert doc["main_studios"] == ["Studio A"] and doc["genres"] == ["Action", "Fantasy"]
    assert doc["start_date"] == {"year": 2020, "month": 10, "day": 4}
    assert doc["relations"] == [
        {"type": "SEQUEL", "id": "anilist:5003", "media_type": "ANIME", "format": "TV"},
        {"type": "ADAPTATION", "id": "anilist:777", "media_type": "MANGA", "format": "MANGA"}]
    # analysis-only fields keep the current_ prefix so they cannot be mistaken for features
    assert doc["current_average_score"] == 81 and doc["current_popularity"] == 45000
    assert "popularity" not in doc and "average_score" not in doc
    assert doc["eligible"] is True and doc["exclusion_reasons"] == [] and doc["listed_at"] == LISTED

    ineligible = candidates.to_candidate_doc(second, LISTED)
    assert ineligible["eligible"] is False
    assert ineligible["exclusion_reasons"] == ["episodes_unknown", "duration_unknown", "not_finished"]
    assert ineligible["end_date"] is None and ineligible["relations"] == [] and ineligible["mal_id"] is None


def test_dedupe_keeps_each_show_once_in_order():
    shows = [{"id": 3}, {"id": 1}, {"id": 3}, {"id": 2}, {"id": 1}]
    assert [m["id"] for m in candidates.dedupe_by_id(shows)] == [3, 1, 2]


# --- listing, with the network call replaced ---------------------------------

def fake_pages(pages):
    """A fake post_query that returns the given pages in order, recording the variables it got."""
    calls = []

    def fake(query, variables=None):
        calls.append(variables)
        media = pages[variables["page"] - 1]
        return {"Page": {"pageInfo": {"hasNextPage": variables["page"] < len(pages)}, "media": media}}

    return fake, calls


def test_list_season_follows_pages_and_removes_repeats(monkeypatch):
    fake, calls = fake_pages([[{"id": 1}, {"id": 2}], [{"id": 2}, {"id": 3}]])  # id 2 shifted onto page 2
    monkeypatch.setattr(anilist, "post_query", fake)
    shows, per_page = candidates.list_season("FALL", 2018, anilist.stats["requests"])
    assert [m["id"] for m in shows] == [1, 2, 3] and per_page == 50
    assert [c["page"] for c in calls] == [1, 2]
    assert all(c["season"] == "FALL" and c["seasonYear"] == 2018 for c in calls)
    assert set(calls[0]) == {"season", "seasonYear", "page", "perPage"}  # no null filters


def test_complexity_error_restarts_the_season_with_25_per_page(monkeypatch):
    seen = []

    def fake(query, variables=None):
        seen.append(variables["perPage"])
        if variables["perPage"] == 50:
            raise anilist.AniListError("AniList returned an error (HTTP 400): Query complexity too high")
        return {"Page": {"pageInfo": {"hasNextPage": False}, "media": [{"id": 9}]}}

    monkeypatch.setattr(anilist, "post_query", fake)
    shows, per_page = candidates.list_season("SPRING", 2020, anilist.stats["requests"])
    assert per_page == 25 and [m["id"] for m in shows] == [9] and seen == [50, 25]


def test_other_errors_are_not_swallowed(monkeypatch):
    def fake(query, variables=None):
        raise anilist.AniListError("AniList returned an error (HTTP 400): Illegal operator and value combination.")

    monkeypatch.setattr(anilist, "post_query", fake)
    with pytest.raises(anilist.AniListError, match="Illegal operator"):
        candidates.list_season("FALL", 2018, anilist.stats["requests"])


def test_request_cap_stops_before_the_next_request(monkeypatch):
    fake, calls = fake_pages([[{"id": 1}]])
    monkeypatch.setattr(anilist, "post_query", fake)
    # the cap is 1 and one request was already used since the start: no request may be made
    with pytest.raises(candidates.RequestBudgetExceeded, match="cap of 1"):
        candidates.list_season("FALL", 2018, anilist.stats["requests"] - 1, request_cap=1)
    assert calls == []


def test_dry_run_prints_the_plan_and_makes_no_requests(capsys):
    collector.dry_run()
    out = capsys.readouterr().out
    assert "32 seasons, FALL 2018 ... SUMMER 2026" in out
    assert "0 requests" in out
    assert "listing <= 100" in out and "hard cap for the task 120" in out
