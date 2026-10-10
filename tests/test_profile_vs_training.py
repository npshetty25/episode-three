"""Tests for the pure helpers in scripts/profile_vs_training.py, on tiny hand-made data."""
import pandas as pd

from scripts.profile_vs_training import (
    compare_with_training,
    drop_rate,
    labelled_entries,
    percentile_rank,
    position_description,
    training_user_stats,
)

TITLES = {
    "anilist:1": {"format": "TV", "is_adult": False, "episodes": 12},
    "anilist:2": {"format": "TV", "is_adult": True, "episodes": 12},      # adult: excluded
    "anilist:3": {"format": "MOVIE", "is_adult": False, "episodes": 1},   # not TV: excluded
    "anilist:4": {"format": "TV_SHORT", "is_adult": False, "episodes": 24},
    "anilist:5": {"format": "TV", "is_adult": False, "episodes": 1},      # one episode
}


def entry(title_id, code):
    return {"title_id": title_id, "mal_status_code": code}


ENTRIES = [entry("anilist:1", 2), entry("anilist:1", 4), entry("anilist:2", 2), entry("anilist:3", 2),
           entry("anilist:4", 4), entry("anilist:5", 2), entry("anilist:1", 6), entry("anilist:9", 2)]


def test_labelled_entries_keeps_tv_non_adult_completed_or_dropped():
    kept = labelled_entries(ENTRIES, TITLES)
    assert [(e["title_id"], e["mal_status_code"]) for e in kept] == [
        ("anilist:1", 2), ("anilist:1", 4), ("anilist:5", 2)]  # planning, unknown title, adult, movie dropped


def test_min_episodes_and_tv_short_selection():
    assert len(labelled_entries(ENTRIES, TITLES, min_episodes=2)) == 2
    assert [e["title_id"] for e in labelled_entries(ENTRIES, TITLES, formats=("TV_SHORT",))] == ["anilist:4"]


def test_drop_rate_and_percentile_rank():
    assert drop_rate(labelled_entries(ENTRIES, TITLES)) == 1 / 3
    assert drop_rate([]) == 0.0
    assert percentile_rank([1, 2, 3, 4], 3) == 75.0
    assert percentile_rank([1, 2, 3, 4], 10) == 100.0
    assert percentile_rank([1, 2, 3, 4], 0) == 0.0


def test_position_is_reported_inside_or_outside_the_training_range():
    sample = pd.DataFrame({
        "user_id": [1] * 20 + [2] * 50,
        "anime_id": list(range(70)),
        "watching_status": [2] * 20 + [2] * 45 + [4] * 5,
    })
    training = training_user_stats(sample)  # user 1: 20 entries, 0% dropped; user 2: 50 entries, 10%
    assert list(training["entries"]) == [20, 50]

    inside = compare_with_training([entry("anilist:1", 2)] * 30, training)
    assert inside["count_in_range"] and inside["users_more_entries"] == 1
    assert position_description(inside, 20, 50).startswith("Inside the training range")

    above = compare_with_training([entry("anilist:1", 2)] * 80 + [entry("anilist:1", 4)] * 20, training)
    assert not above["count_in_range"] and above["users_more_entries"] == 0
    assert position_description(above, 20, 50).startswith("OUTSIDE the training range")
