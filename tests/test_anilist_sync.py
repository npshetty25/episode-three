"""Offline tests for episode_three/anilist_sync.py, using hand-made fixtures."""
from datetime import datetime, timedelta, timezone

import pytest

from episode_three import anilist_sync
from episode_three.clients import anilist
from tests.conftest import load_fixture

SYNCED = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def sample_chunks():
    return [load_fixture("anilist_list_collection_sample.json")["MediaListCollection"]]


def sample_docs(changed_at=SYNCED):
    # The 7-entry fixture has a "burst" of 4 entries in one minute, so lower the threshold to 4.
    entries = anilist_sync.unique_entries(sample_chunks())
    docs = anilist_sync.build_entry_docs(entries, "testuser", changed_at, min_burst=4)
    return {entry["id"]: doc for entry, doc in zip(entries, docs)}


def test_status_mapping_matches_mal_codes():
    assert anilist_sync.STATUS_TO_MAL_CODE == {
        "CURRENT": 1, "COMPLETED": 2, "REPEATING": 2, "PAUSED": 3, "DROPPED": 4, "PLANNING": 6}
    docs = sample_docs()
    assert docs[1002]["mal_status_code"] == 2 and docs[1002]["repeating"] is True
    assert docs[1001]["repeating"] is False
    assert {d["anilist_status"] for d in docs.values()} == set(anilist_sync.STATUS_TO_MAL_CODE)


def test_unknown_status_is_a_clear_error():
    entry = anilist_sync.unique_entries(sample_chunks())[0] | {"status": "WATCHING_LATER"}
    with pytest.raises(ValueError, match="WATCHING_LATER"):
        anilist_sync.to_entry_doc(entry, "testuser", SYNCED, "anilist")


def test_score_zero_means_unscored():
    docs = sample_docs()
    assert docs[1001]["score_100"] == 85
    assert docs[1003]["score_100"] is None


def test_fuzzy_dates():
    assert anilist_sync.fuzzy_date({"year": None, "month": None, "day": None}) is None
    assert anilist_sync.fuzzy_date(None) is None
    assert anilist_sync.fuzzy_date({"year": 2025, "month": None, "day": None}) == {"year": 2025, "month": None, "day": None}
    docs = sample_docs()
    assert docs[1001]["started_at"] == {"year": 2024, "month": 1, "day": 2}
    assert docs[1003]["started_at"] is None


def test_entry_in_custom_list_is_counted_once():
    entries = anilist_sync.unique_entries(sample_chunks())
    assert len(entries) == 7
    assert [e["id"] for e in entries].count(1003) == 1


def fake_entries(created_at_list):
    """Minimal entries: just an id and a createdAt (unix seconds), enough for the origin rule."""
    return [{"id": number, "createdAt": created} for number, created in enumerate(created_at_list, 1)]


def origins(created_at_list):
    entries = fake_entries(created_at_list)
    bursts = anilist_sync.import_burst_minutes(entries)
    return [anilist_sync.entry_origin(e["createdAt"], bursts) for e in entries]


IMPORT_MINUTE = int(datetime(2026, 10, 10, 12, 59, tzinfo=timezone.utc).timestamp())
OTHER_MINUTE = int(datetime(2026, 10, 8, 8, 57, tzinfo=timezone.utc).timestamp())


def test_burst_of_60_is_an_import_and_single_entries_are_not():
    burst = [IMPORT_MINUTE + (i % 60) for i in range(60)]  # 60 entries within one minute
    singles = [IMPORT_MINUTE + 86_400 * (day + 1) for day in range(3)]  # one per later day
    assert origins(burst + singles) == ["mal_import"] * 60 + ["anilist"] * 3


def test_burst_just_under_the_threshold_is_not_an_import():
    assert anilist_sync.IMPORT_BURST_MIN_ENTRIES == 50
    assert origins([IMPORT_MINUTE + (i % 60) for i in range(49)]) == ["anilist"] * 49
    assert origins([IMPORT_MINUTE + (i % 60) for i in range(50)]) == ["mal_import"] * 50


def test_two_separate_bursts_are_both_imports():
    first = [OTHER_MINUTE + (i % 60) for i in range(55)]
    second = [IMPORT_MINUTE + (i % 60) for i in range(70)]
    manual = [IMPORT_MINUTE + 7200]
    assert origins(first + second + manual) == ["mal_import"] * 125 + ["anilist"]


def test_missing_created_at_counts_as_import():
    assert origins([None, 0, IMPORT_MINUTE]) == ["mal_import", "mal_import", "anilist"]


def test_origin_in_the_fixture():
    docs = sample_docs()  # threshold lowered to 4: four entries share one minute, three share another
    assert docs[1001]["origin"] == "mal_import" and docs[1004]["origin"] == "mal_import"
    assert docs[1002]["origin"] == "anilist" and docs[1007]["origin"] == "anilist"


def test_empty_list_gives_no_entries():
    chunks = [load_fixture("anilist_list_collection_empty.json")["MediaListCollection"]]
    assert anilist_sync.unique_entries(chunks) == []


def test_plan_finds_new_changed_unchanged_and_removed():
    fresh = list(sample_docs().values())
    stored = [dict(d) for d in fresh[:4]]
    stored[0]["progress"] = 999  # will count as changed
    stored.append({"_id": "anilist_entry:9999", "username": "testuser"})  # gone from AniList
    plan = anilist_sync.plan_changes(stored, fresh)
    assert len(plan["new"]) == 3
    assert [d["_id"] for d in plan["changed"]] == [fresh[0]["_id"]]
    assert len(plan["unchanged"]) == 3
    assert plan["removed"] == ["anilist_entry:9999"]


def test_second_sync_of_same_data_changes_nothing():
    first = list(sample_docs(SYNCED).values())
    later = list(sample_docs(SYNCED + timedelta(hours=1)).values())  # only content_changed_at differs
    plan = anilist_sync.plan_changes(first, later)
    assert plan["new"] == [] and plan["changed"] == [] and plan["removed"] == []
    assert len(plan["unchanged"]) == 7


def test_title_docs_have_prefixed_ids_and_no_personal_fields():
    media = anilist_sync.unique_entries(sample_chunks())[0]["media"]
    doc = anilist_sync.to_title_doc(media, SYNCED)
    assert doc["_id"] == "anilist:21" and doc["mal_id"] == 21
    assert "progress" not in doc and "score_100" not in doc


def test_fetch_list_turns_unknown_user_into_a_clear_error(monkeypatch):
    real = load_fixture("anilist_unknown_user_response.json")
    message = real["body"]["errors"][0]["message"]

    def fake_post_query(query, variables=None):
        raise anilist.AniListError(f"AniList returned an error (HTTP {real['http_status']}): {message}")

    monkeypatch.setattr(anilist, "post_query", fake_post_query)
    with pytest.raises(anilist.AniListError, match="no user named 'ghost'"):
        anilist_sync.fetch_list("ghost")


def test_failed_ping_means_anilist_is_never_called():
    calls = []

    def failing_ping(database):
        calls.append("ping")
        raise RuntimeError("Atlas unreachable")

    def fetch(username):
        calls.append("fetch")
        return []

    with pytest.raises(RuntimeError, match="Atlas unreachable"):
        anilist_sync.sync(None, "testuser", ping=failing_ping, fetch=fetch)
    assert calls == ["ping"]


def test_ping_comes_before_the_fetch():
    calls = []

    class Stop(Exception):
        pass

    def ping(database):
        calls.append("ping")

    def fetch(username):
        calls.append("fetch")
        raise Stop  # stop here: this test only checks the order

    with pytest.raises(Stop):
        anilist_sync.sync(None, "testuser", ping=ping, fetch=fetch)
    assert calls == ["ping", "fetch"]


def test_fetch_list_follows_chunks(monkeypatch):
    calls = []

    def fake_post_query(query, variables=None):
        calls.append(variables["chunk"])
        return {"MediaListCollection": {"hasNextChunk": variables["chunk"] < 2, "user": {}, "lists": []}}

    monkeypatch.setattr(anilist, "post_query", fake_post_query)
    assert len(anilist_sync.fetch_list("someone")) == 2
    assert calls == [1, 2]


def test_stale_entries_and_missing_dates():
    docs = list(sample_docs().values())
    titles = {"anilist:24": {"title": {"english": "Show D EN"}, "episodes": None}}
    now = datetime(2027, 6, 1, tzinfo=timezone.utc)  # 180+ days after every updatedAt
    stale = anilist_sync.stale_entries(docs, titles, now)
    assert [(row["status"], row["title"]) for row in stale] == [("CURRENT", "Show D EN"), ("PAUSED", "anilist:25")]
    assert stale[1]["reason"] == "not updated in 180 days"
    assert anilist_sync.count_without_dates(docs) == 3


def matches(mongo_filter, doc):
    """Evaluate the simple filters the sync uses (equality and $in) against one document."""
    for field, condition in mongo_filter.items():
        value = doc.get(field)
        if isinstance(condition, dict):
            assert set(condition) == {"$in"}, f"unexpected operator in {condition}"
            if value not in condition["$in"]:
                return False
        elif value != condition:
            return False
    return True


MANUAL_ENTRY = {"_id": "manual_entry:tvmaze:169", "source": "manual", "title_id": "tvmaze:169",
                "media_type": "tv", "status": "watching", "mal_status_code": 1}


def test_entry_docs_are_tagged_anilist_with_content_changed_at():
    doc = sample_docs()[1001]
    assert doc["source"] == "anilist"
    assert doc["content_changed_at"] == SYNCED and "synced_at" not in doc


def test_deletion_filter_can_never_match_a_manual_entry():
    # Worst case: the manual entry's _id is on the delete list and it even carries the username.
    manual = dict(MANUAL_ENTRY, username="testuser")
    anilist_doc = sample_docs()[1001]
    other_user = dict(anilist_doc, username="someone_else")
    deletion = anilist_sync.entry_deletion_filter("testuser", [manual["_id"], anilist_doc["_id"], other_user["_id"]])
    assert not matches(deletion, manual)
    assert not matches(deletion, MANUAL_ENTRY)
    assert not matches(deletion, other_user)
    assert matches(deletion, anilist_doc)


def test_manual_entries_are_never_planned_for_removal():
    anilist_docs = list(sample_docs().values())
    everything_in_my_entries = anilist_docs + [MANUAL_ENTRY]
    stored = [d for d in everything_in_my_entries if matches(anilist_sync.stored_entries_filter("testuser"), d)]
    fresh = anilist_docs[1:]  # the first AniList entry was deleted on AniList
    plan = anilist_sync.plan_changes(stored, fresh)
    assert plan["removed"] == [anilist_docs[0]["_id"]]


def test_imported_entry_leaves_the_stale_report_once_edited():
    docs = list(sample_docs().values())
    show_d = next(d for d in docs if d["_id"] == "anilist_entry:1004")  # imported CURRENT, untouched
    recent = show_d["created_at"] + timedelta(days=1)
    now = recent + timedelta(days=2)  # far less than 180 days after the edit
    assert [r["title"] for r in anilist_sync.stale_entries([show_d], {}, now)] == ["anilist:24"]
    assert anilist_sync.untouched_import(show_d) is True

    edited = dict(show_d, updated_at=show_d["created_at"] + timedelta(seconds=147))  # like One Piece
    assert anilist_sync.untouched_import(edited) is False
    assert anilist_sync.stale_entries([edited], {}, now) == []
