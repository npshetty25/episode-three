"""Offline tests for episode_three/collect/kaggle_import.py."""
import numpy as np
import pandas as pd
import pytest

from episode_three.collect import kaggle_import as ki


def doc(anilist_id, mal_id, fmt="TV", adult=False):
    return {"_id": f"anilist:{anilist_id}", "anilist_id": anilist_id, "mal_id": mal_id, "format": fmt, "is_adult": adult}


DOCS = [doc(1, 10), doc(2, 20, "TV_SHORT"), doc(3, 30, None), doc(4, 40, adult=True),
        doc(5, 50), doc(6, 50), doc(7, 70, "ONA")]                     # mal 50 maps to two AniList entries
ANIME_MAP = ki.classify_anime(DOCS, unmapped_mal_ids=[60])


def rows(*triples):
    return pd.DataFrame(triples, columns=["user_id", "anime_id", "watching_status"])


def test_classification_of_each_anime():
    assert ANIME_MAP[10] == {"reason": None, "sub": None, "anilist_id": 1}
    assert ANIME_MAP[20]["reason"] == "format_not_tv" and ANIME_MAP[20]["sub"] == "TV_SHORT"
    assert ANIME_MAP[30]["reason"] == "format_unknown"
    assert ANIME_MAP[40]["reason"] == "adult"
    assert ANIME_MAP[50]["reason"] == "ambiguous_mapping" and ANIME_MAP[50]["anilist_id"] is None
    assert ANIME_MAP[60]["reason"] == "unmapped" and ANIME_MAP[70]["sub"] == "ONA"


def test_every_exclusion_reason_is_applied_and_counted():
    sample = rows((1, 10, 2), (1, 20, 2), (1, 30, 4), (1, 40, 2), (1, 50, 2), (1, 60, 4), (1, 70, 2), (1, 999, 2),   # one row per anime reason
                  (2, 10, 1), (2, 10, 33), (2, 10, 0),                                                              # bad status codes
                  (3, 10, 2), (3, 10, 4))                                                                           # a duplicate pair
    kept, funnel = ki.apply_filters(sample, ANIME_MAP)
    by_reason = {step["reason"]: step for step in funnel}
    assert [s["reason"] for s in funnel] == list(ki.REASONS)
    assert by_reason["bad_status_code"]["rows_removed"] == 3 and by_reason["bad_status_code"]["subs"] == {"0": 1, "1": 1, "33": 1}
    assert by_reason["duplicate_pair"]["rows_removed"] == 1
    assert by_reason["unmapped"]["rows_removed"] == 2 and by_reason["unmapped"]["subs"] == {"not_fetched": 1}   # mal 60 and the unknown mal 999
    assert by_reason["ambiguous_mapping"]["rows_removed"] == 1
    assert by_reason["format_unknown"]["rows_removed"] == 1
    assert by_reason["format_not_tv"]["rows_removed"] == 2 and by_reason["format_not_tv"]["subs"] == {"ONA": 1, "TV_SHORT": 1}
    assert by_reason["adult"]["rows_removed"] == 1
    assert sorted(zip(kept["user_id"], kept["mal_id"], kept["anilist_id"], kept["status"])) == [(1, 10, 1, "completed"), (3, 10, 1, "completed")]
    assert funnel[-1]["rows_after"] == len(kept) == 2 and sum(s["rows_removed"] for s in funnel) == len(sample) - 2


def test_an_ambiguous_mapping_is_excluded_not_guessed():
    kept, funnel = ki.apply_filters(rows((1, 50, 2)), ANIME_MAP)
    assert kept.empty and {s["reason"]: s["rows_removed"] for s in funnel}["ambiguous_mapping"] == 1


def test_users_below_the_minimum_are_dropped():
    data = pd.DataFrame({"user_id": [1] * 20 + [2] * 19, "mal_id": list(range(20)) + list(range(19)),
                         "anilist_id": list(range(20)) + list(range(19)), "status": ["completed"] * 39})
    kept, users_removed, rows_removed = ki.filter_users(data)
    assert set(kept["user_id"]) == {1} and (users_removed, rows_removed) == (1, 19)


# --- user split ------------------------------------------------------------------------------------------------------------------

def test_user_split_proportions_and_disjointness():
    ids = list(range(1000, 5987))                                   # 4,987 users, as expected
    splits = ki.split_users(ids)
    counts = pd.Series(splits).value_counts().to_dict()
    assert counts == {"train": 3491, "validation": 748, "test": 748} and len(splits) == 4987
    assert set(splits) == set(ids)                                  # every user in exactly one split (a dict key is unique)
    assert ki.split_users(ids[::-1]) == splits                      # input order does not matter
    assert ki.split_users(ids) == splits                            # deterministic
    assert ki.split_users(ids, seed=7) != splits


def test_user_split_is_a_permutation_of_the_sorted_ids():
    ids = [5, 3, 9, 1, 7, 11, 13, 15, 17, 19]
    expected = np.array(sorted(ids))[np.random.default_rng(42).permutation(10)]
    splits = ki.split_users(ids)
    assert [u for u, s in splits.items() if s == "train"] == [int(u) for u in expected[:7]]     # round(0.7 * 10) = 7


# --- history / target ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("n,expected", [(20, 4), (21, 4), (24, 4), (25, 5), (4434, 886), (1, 1), (4, 1)])
def test_target_count_rule(n, expected):
    assert ki.target_count(n) == expected


def test_every_user_has_a_target_and_a_history_entry():
    for n in (20, 21, 100, 4434):
        roles = ki.split_history_target(list(range(n)), user_id=3)
        assert list(roles.values()).count("target") == ki.target_count(n) >= 1
        assert list(roles.values()).count("history") == n - ki.target_count(n) >= 1


def test_a_users_roles_do_not_change_when_other_users_change():
    anime = list(range(100, 140))
    alone = ki.split_history_target(anime, user_id=77)
    assert ki.split_history_target(list(reversed(anime)), user_id=77) == alone            # entry order does not matter
    assert ki.split_history_target(anime, user_id=78) != alone                               # another user, another split
    kept = pd.DataFrame({"user_id": [77] * 40 + [5] * 25, "mal_id": anime + list(range(25)),
                         "anilist_id": anime + list(range(25)), "status": ["completed"] * 65})
    both = {d["_id"]: d for d in ki.build_documents(kept)}
    only_77 = {d["_id"]: d for d in ki.build_documents(kept[kept["user_id"] == 77])}
    assert both["mal_user:77"]["entries"] == only_77["mal_user:77"]["entries"]           # removing user 5 changed nothing for 77
    assert {e["mal_id"]: e["role"] for e in both["mal_user:77"]["entries"]} == alone


# --- documents --------------------------------------------------------------------------------------------------------------------

def fixture_kept():
    users = {10: 22, 11: 25, 12: 20, 13: 30, 14: 21}
    rows_ = [(u, m, 100 + m, "dropped" if m % 7 == 0 else "completed") for u, n in users.items() for m in range(n)]
    return pd.DataFrame(rows_, columns=["user_id", "mal_id", "anilist_id", "status"])


def test_stored_entries_have_exactly_the_four_allowed_keys():
    docs = ki.build_documents(fixture_kept())
    for d in docs:
        assert set(d) == {"_id", "split", "n_entries", "n_history", "n_target", "entries"}
        assert d["n_entries"] == len(d["entries"]) == d["n_history"] + d["n_target"] and d["n_target"] >= 1 and d["n_history"] >= 1
        for entry in d["entries"]:
            assert tuple(entry) == ki.ENTRY_KEYS and entry["anime_id"] == f"anilist:{100 + entry['mal_id']}"
            assert entry["status"] in ("completed", "dropped") and entry["role"] in ("history", "target")
    assert docs[0]["_id"] == "mal_user:10"


def test_building_documents_twice_gives_identical_content_and_a_valid_split():
    kept = fixture_kept()
    first, second = ki.build_documents(kept), ki.build_documents(kept.sample(frac=1, random_state=1))
    assert first == second                                                  # idempotent, independent of row order
    stats = ki.split_statistics(first)
    assert sum(s["users"] for s in stats.values()) == 5 and stats["train"]["users"] == round(0.7 * 5)


def test_funnel_markdown_is_deterministic_and_adds_up():
    kept = fixture_kept()
    docs = ki.build_documents(kept)
    funnel = [{"reason": r, "rows_removed": 0, "rows_after": len(kept), "subs": {}} for r in ki.REASONS]
    nirav = {"labelled": 4181, "dropped": 126, "drop_rate": 126 / 4181, "mal_non_tv": 11, "mal_non_tv_types": {"ONA": 4}, "not_in_2020_csv": 864}
    text = ki.funnel_markdown(len(kept), 5, funnel, 0, 0, docs, nirav)
    assert text == ki.funnel_markdown(len(kept), 5, funnel, 0, 0, docs, nirav)
    assert "4,181" in text and "3.0%" in text and "not** redrawn" in text
    assert "| train |" in text and "Disclosures" in text
