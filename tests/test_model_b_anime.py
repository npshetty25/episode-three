"""Offline tests for episode_three/collect/model_b_anime.py."""
import pytest

from episode_three.clients import anilist
from episode_three.collect import model_b_anime as mba


def title(anilist_id, mal_id, fmt="TV", adult=False):
    return {"_id": f"anilist:{anilist_id}", "anilist_id": anilist_id, "mal_id": mal_id, "format": fmt, "is_adult": adult}


def entry(anilist_id, status):
    return {"title_id": f"anilist:{anilist_id}", "anilist_status": status}


TITLES = {t["_id"]: t for t in [
    title(1, 101), title(2, 102), title(3, 103, "MOVIE"), title(4, 104), title(5, None), title(6, 106, adult=True),
    title(7, 107, "OVA"), title(8, 108)]}
ENTRIES = [entry(1, "COMPLETED"), entry(2, "DROPPED"), entry(3, "COMPLETED"),   # a completed MOVIE: not a feature entry
           entry(4, "PLANNING"), entry(5, "CURRENT"), entry(6, "COMPLETED"),    # adult: skipped
           entry(7, "PLANNING"),                                                # planned OVA: kept (a prediction target)
           entry(8, "PAUSED")]                                                  # paused: neither


def test_nirav_titles_follow_the_ruling():
    chosen = mba.nirav_titles(ENTRIES, TITLES)
    assert sorted(chosen) == ["anilist:1", "anilist:2", "anilist:4", "anilist:5", "anilist:7"]


def test_universe_deduplicates_and_uses_both_id_routes():
    universe = mba.build_universe([101, 150, 150, 160], ENTRIES, TITLES)
    # Kaggle {101, 150, 160} + Nirav's mal ids {101, 102, 104, 107}; title 5 has no mal_id -> the id_in route
    assert universe["mal_ids"] == [101, 102, 104, 107, 150, 160] and universe["anilist_ids"] == [5]
    assert (universe["kaggle"], universe["nirav"], universe["overlap"], universe["total"]) == (3, 5, 1, 7)
    assert universe["total"] == len(universe["mal_ids"]) + len(universe["anilist_ids"])


def test_chunking_and_request_plan():
    ids = list(range(120))
    chunks = mba.chunk(ids, 50)
    assert [len(c) for c in chunks] == [50, 50, 20] and sum(chunks, []) == ids
    assert mba.chunk([], 50) == []
    assert mba.planned_requests(120, 0) == 3 and mba.planned_requests(100, 1) == 3 and mba.planned_requests(0, 0) == 0
    assert mba.planned_requests(51, 0, per_page=25) == 3


def test_resumability_skips_stored_and_unmapped_unless_forced():
    universe = {"mal_ids": [1, 2, 3, 4], "anilist_ids": [10, 11]}
    assert mba.todo_ids(universe, stored_mal_ids=[1], stored_anilist_ids=[10], unmapped_mal_ids=[3]) == ([2, 4], [11])
    assert mba.todo_ids(universe, [1, 2, 3, 4], [10, 11], []) == ([], [])
    assert mba.todo_ids(universe, [1, 2, 3, 4], [10, 11], [], force=True) == ([1, 2, 3, 4], [10, 11])


def media(anilist_id=7, mal_id=70, distribution=None, **extra):
    base = {"id": anilist_id, "idMal": mal_id, "format": "TV", "status": "FINISHED", "episodes": 12, "duration": 24,
            "source": "MANGA", "countryOfOrigin": "JP", "isAdult": False, "genres": ["Action"], "averageScore": 75,
            "popularity": 5000, "startDate": {"year": 2018},
            "stats": {"statusDistribution": distribution if distribution is not None else [
                {"status": "CURRENT", "amount": 50}, {"status": "COMPLETED", "amount": 900}, {"status": "DROPPED", "amount": 100},
                {"status": "PLANNING", "amount": 700}]}}
    base.update(extra)
    return base


def test_document_mapping_uses_prefixed_ids_and_computes_drop_share():
    doc = mba.to_model_b_anime_doc(media())
    assert doc["_id"] == "anilist:7" and doc["anilist_id"] == 7 and doc["mal_id"] == 70 and doc["start_year"] == 2018
    assert doc["status_distribution"] == {"CURRENT": 50, "COMPLETED": 900, "DROPPED": 100, "PLANNING": 700}
    assert doc["drop_share"] == pytest.approx(0.1)                       # 100 / (900 + 100)
    assert set(doc) == {"_id", "anilist_id", "mal_id", "format", "status", "episodes", "duration_min", "source_material",
                        "country", "is_adult", "genres", "start_year", "average_score", "popularity",
                        "status_distribution", "drop_share"}             # no other stats are stored


def test_drop_share_is_null_when_the_denominator_is_zero():
    assert mba.drop_share({}) is None
    assert mba.drop_share({"CURRENT": 10, "PLANNING": 5}) is None
    assert mba.drop_share({"DROPPED": 3}) == 1.0 and mba.drop_share({"COMPLETED": 4}) == 0.0
    assert mba.to_model_b_anime_doc(media(distribution=[]))["drop_share"] is None
    assert mba.to_model_b_anime_doc(media(stats=None))["status_distribution"] == {}
    assert mba.to_model_b_anime_doc(media(startDate=None))["start_year"] is None


def test_unmapped_mal_ids_are_recorded_not_dropped():
    rows = [media(1, 10), media(2, 20)]
    docs, unmapped = mba.split_answer([10, 20, 30, 40], rows, by_mal_id=True)
    assert [d["mal_id"] for d in docs] == [10, 20]
    assert [u["_id"] for u in unmapped] == ["mal:30", "mal:40"] and unmapped[0]["mal_id"] == 30
    docs, unmapped = mba.split_answer([1, 2, 3], rows, by_mal_id=False)       # the id_in route has no MAL ids to record
    assert len(docs) == 2 and unmapped == []


def test_queries_name_only_the_filter_they_use():
    assert "idMal_in: $malIds" in mba.QUERY_BY_MAL_ID and "id_in" not in mba.QUERY_BY_MAL_ID
    assert "id_in: $ids" in mba.QUERY_BY_ANILIST_ID and "idMal_in" not in mba.QUERY_BY_ANILIST_ID
    for text in (mba.QUERY_BY_MAL_ID, mba.QUERY_BY_ANILIST_ID):
        assert "statusDistribution { status amount }" in text and "type: ANIME" in text
        assert "perPage: $perPage" in text and "hasNextPage" in text


def test_fetch_chunk_stops_without_an_extra_request_when_every_id_is_answered(monkeypatch):
    requested = []

    def fake(query, variables=None):
        requested.append(variables)
        rows = [media(i, i * 10) for i in range(1, 4)]
        return {"Page": {"pageInfo": {"hasNextPage": True}, "media": rows}}      # AniList says "more" on a full page

    monkeypatch.setattr(anilist, "post_query", fake)
    rows = mba.fetch_chunk([10, 20, 30], by_mal_id=True, per_page=3)
    assert len(rows) == 3 and len(requested) == 1                                  # is_complete saved the second request
    assert requested[0] == {"malIds": [10, 20, 30], "perPage": 3, "page": 1}
    requested.clear()
    mba.fetch_chunk([1, 2, 3], by_mal_id=False, per_page=3)
    assert requested[0]["ids"] == [1, 2, 3]
