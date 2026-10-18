"""Offline tests for episode_three/features/tv_filters.py."""
import pandas as pd
import pytest

from episode_three.features import tv_filters as tf


def sample_frame():
    """3 users: u1 has 3 rows, u2 has 2, u3 has 1. Anime 1, 2 are AniList TV; 3 is OVA on AniList; 4 is unmapped."""
    rows = [(1, 1, 2), (1, 2, 2), (1, 3, 4), (2, 1, 2), (2, 4, 4), (3, 3, 2)]
    return pd.DataFrame(rows, columns=["user_id", "anime_id", "watching_status"])


ANILIST = {1: "TV", 2: "TV", 3: "OVA"}                                  # 4 is unmapped
MAL = {1: "TV", 2: "TV", 3: "TV", 4: "TV"}


def test_filter_scenarios_count_rows_anime_and_users():
    result = tf.filter_scenarios(sample_frame(), ANILIST, MAL, min_entries=2)
    assert result["i_mal_tv"]["rows"] == 6 and result["i_mal_tv"]["anime"] == 4
    assert result["i_mal_tv"]["users_kept"] == 2 and result["i_mal_tv"]["users_below_min"] == 1       # u3 has 1 row
    ii = result["ii_anilist_tv"]
    assert ii["rows"] == 3 and ii["anime"] == 2                                                     # anime 3 and 4 are dropped
    assert ii["users_kept"] == 1 and ii["users_below_min"] == 2                                     # only u1 keeps >= 2 rows
    assert ii["drop_rate"] == 0.0 and result["i_mal_tv"]["drop_rate"] == pytest.approx(2 / 6)
    assert result["iii_both"] == result["ii_anilist_tv"]                                            # the sample is all MAL TV


def test_both_differs_when_mal_type_is_not_tv():
    result = tf.filter_scenarios(sample_frame(), ANILIST, {1: "TV", 2: "OVA", 3: "TV", 4: "TV"}, min_entries=1)
    assert result["iii_both"]["rows"] == 2 and result["ii_anilist_tv"]["rows"] == 3 and result["i_mal_tv"]["rows"] == 5


def test_mal_tv_by_anilist_format_includes_unmapped():
    out = tf.mal_tv_by_anilist_format(sample_frame(), ANILIST)
    assert out["anime"] == {"TV": 2, "OVA": 1, tf.UNMAPPED: 1} and out["rows"]["TV"] == 3 and out["rows"][tf.UNMAPPED] == 1


def test_coverage():
    docs = {1: {"drop_share": 0.1}, 2: {"drop_share": None}, 3: {"drop_share": 0.5}}
    c = tf.coverage(sample_frame(), docs)
    assert (c["rows"], c["rows_with_record"], c["rows_with_drop_share"]) == (6, 5, 4)
    assert (c["anime"], c["anime_with_record"], c["anime_with_drop_share"]) == (4, 3, 2)


def test_unknown_episode_tv():
    csv = pd.DataFrame({"MAL_ID": [1, 2, 3, 4], "Type": ["TV", "TV", "TV", "OVA"], "Episodes": [None, None, 12, None]})
    out = tf.unknown_episode_tv(csv, {1: {"episodes": 24}, 9: {"episodes": 1}})
    assert out == {"mal_tv_unknown_episodes": 2, "fetched": 1, "with_episodes_on_anilist": 1, "not_fetched": 1, "ids_not_fetched": [2]}


def test_nirav_comparison_counts_mal_non_tv_and_unknown():
    titles = {f"anilist:{i}": {"_id": f"anilist:{i}", "mal_id": i, "format": "TV", "is_adult": False} for i in (1, 2, 3, 4)}
    titles["anilist:5"] = {"_id": "anilist:5", "mal_id": 5, "format": "MOVIE", "is_adult": False}
    entries = [{"title_id": f"anilist:{i}", "mal_status_code": c} for i, c in ((1, 2), (2, 4), (3, 2), (4, 2), (5, 2))]

    def labelled(entries, titles_by_id, formats):
        return [e for e in entries if titles_by_id[e["title_id"]]["format"] in formats]

    drop = lambda kept: sum(1 for e in kept if e["mal_status_code"] == 4) / len(kept)
    out = tf.nirav_comparison(entries, titles, {1: "TV", 2: "TV", 3: "OVA"}, labelled, drop)
    assert out["labelled"] == 4 and out["dropped"] == 1 and out["drop_rate"] == 0.25      # the MOVIE is not AniList TV
    assert out["mal_non_tv"] == 1 and out["mal_non_tv_types"] == {"OVA": 1} and out["non_tv_mal_ids"] == [3]
    assert out["not_in_2020_csv"] == 1                                                    # mal id 4 is not in anime.csv
    blank = tf.nirav_comparison(entries, titles, {1: "TV", 2: "TV", 3: float("nan"), 4: "TV"}, labelled, drop)
    assert blank["mal_non_tv"] == 0 and blank["not_in_2020_csv"] == 1 and blank["mal_non_tv_types"] == {}   # a blank MAL type is unknown


def test_full_file_scan_counts_only_requested_ids_and_completed_or_dropped(tmp_path):
    path = tmp_path / "animelist.csv"
    pd.DataFrame({"user_id": [1, 1, 2, 2, 3, 3], "anime_id": [10, 20, 10, 10, 20, 30], "rating": [0] * 6,
                  "watching_status": [2, 2, 4, 6, 2, 4], "watched_episodes": [1] * 6}).to_csv(path, index=False)
    out = tf.count_rows_for_ids(path, [10, 30], chunk_rows=2)       # tiny chunks: the totals must not depend on chunking
    assert out["file_rows"] == 6 and out["rows"] == 3 and out["per_anime"] == {10: 2, 30: 1}      # status 6 (plan to watch) skipped
    assert out["anime_with_rows"] == 2 and out["users"] == 3
    assert tf.count_rows_for_ids(path, [10, 30], chunk_rows=100)["per_anime"] == out["per_anime"]


def test_extra_mapping_requests():
    assert tf.extra_mapping_requests(range(1, 101), range(1, 51)) == (50, 1)
    assert tf.extra_mapping_requests(range(1, 102), range(1, 51)) == (51, 2)
    assert tf.extra_mapping_requests([1, 2], [1, 2]) == (0, 0)
