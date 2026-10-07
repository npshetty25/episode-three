"""Tests for the pure helpers in scripts/probe_mal_data.py, on tiny hand-made tables."""
import pandas as pd

from scripts.probe_mal_data import (
    count_labeled_per_user,
    drop_rate_summary,
    eligible_anime_ids,
    genre_list,
    sample_users,
)


def make_anime():
    return pd.DataFrame({
        "MAL_ID": [1, 2, 3, 4, 5, 6],
        "Type": ["TV", "TV", "Movie", "TV", "TV", "TV"],
        "Genres": ["Action, Drama", "Hentai", "Action", "Comedy", None, "Romance"],
        "Rating": ["PG-13 - Teens 13 or older", "Rx - Hentai", "R - 17+", "Rx - Hentai", "G - All Ages", "PG"],
        "Episodes": [12, 2, 1, 24, None, 1],
    })


def test_genre_list_handles_missing_values():
    assert genre_list("Action, Hentai") == ["Action", "Hentai"]
    assert genre_list(None) == []


def test_eligible_anime_ids_keeps_only_tv_non_adult_with_two_or_more_episodes():
    # 2 = Hentai, 3 = Movie, 4 = Rx rating, 5 = unknown episodes, 6 = single episode
    assert eligible_anime_ids(make_anime()) == {1}


def test_count_labeled_per_user_counts_only_completed_or_dropped_eligible_rows():
    chunk = pd.DataFrame({
        "user_id": [7, 7, 7, 7, 8],
        "anime_id": [1, 1, 2, 1, 1],
        "watching_status": [2, 4, 2, 1, 4],  # 1 = watching, not a label
    })
    counts = count_labeled_per_user(chunk, eligible_ids={1})
    assert counts.to_dict() == {7: 2, 8: 1}


def test_sample_users_is_reproducible_and_ignores_input_order():
    counts = pd.Series({user: 25 for user in range(100)} | {500: 3})
    shuffled = counts.sample(frac=1, random_state=1)
    first, eligible = sample_users(counts, min_entries=20, size=10, seed=42)
    again, _ = sample_users(shuffled, min_entries=20, size=10, seed=42)
    assert eligible == 100
    assert list(first) == list(again)
    assert 500 not in first


def test_sample_users_uses_everyone_when_too_few_are_eligible():
    users, eligible = sample_users(pd.Series({1: 30, 2: 40, 3: 5}), min_entries=20, size=10)
    assert eligible == 2
    assert list(users) == [1, 2]


def test_drop_rate_summary():
    sample = pd.DataFrame({
        "user_id": [1, 1, 2, 2],
        "anime_id": [10, 11, 10, 12],
        "watching_status": [2, 4, 2, 2],
    })
    summary = drop_rate_summary(sample)
    assert summary["dropped"] == 1
    assert summary["drop_rate"] == 0.25
    assert summary["share_users_no_drops"] == 0.5
    assert summary["distinct_anime"] == 3
