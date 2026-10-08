"""Live test: really fetches Nirav's AniList list and writes to episode_three_test.

Skipped in normal runs. Run with:  python -m pytest -m live -q
Uses ONE AniList request: the list is fetched once and synced twice.
"""
import pytest

from episode_three import anilist_sync, config, db

pytestmark = pytest.mark.live


def test_sync_twice_changes_nothing_the_second_time():
    database = db.get_client()["episode_three_test"]
    username = config.get_anilist_username()
    chunks = anilist_sync.fetch_list(username)

    first = anilist_sync.sync(database, username, chunks=chunks)
    second = anilist_sync.sync(database, username, chunks=chunks)

    assert first["fetched"] == second["fetched"] > 0
    assert second["inserted"] == 0
    assert second["modified"] == 0
    assert second["deleted"] == 0
    assert second["unchanged"] == second["fetched"]
