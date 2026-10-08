"""Offline tests for the retry logic in episode_three/clients/anilist.py.

The real network is never used: the client's session is swapped for a fake one,
and time.sleep is swapped for a function that only records how long it would wait.
"""
from types import SimpleNamespace

import pytest
import requests

from episode_three.clients import anilist

OK_BODY = {"data": {"Page": {"pageInfo": {"hasNextPage": False}}}}


def fake_response(status, body=None, headers=None):
    return SimpleNamespace(status_code=status, headers=headers or {}, json=lambda: body or {}, text="")


@pytest.fixture
def waits(monkeypatch):
    """Replace sleeping with recording, and start each test with a fresh rate-limit clock."""
    recorded = []
    monkeypatch.setattr(anilist.time, "sleep", recorded.append)
    monkeypatch.setattr(anilist, "_last_request_started", None)
    return recorded


def use_responses(monkeypatch, responses):
    queue = iter(responses)
    monkeypatch.setattr(anilist, "_session", SimpleNamespace(post=lambda *args, **kwargs: next(queue)))


def test_429_waits_for_retry_after_then_succeeds(monkeypatch, waits):
    use_responses(monkeypatch, [fake_response(429, headers={"Retry-After": "7"}), fake_response(200, OK_BODY)])
    assert anilist.post_query("query { x }") == OK_BODY["data"]
    assert 7 in waits


def test_429_without_retry_after_waits_the_default(monkeypatch, waits):
    use_responses(monkeypatch, [fake_response(429), fake_response(200, OK_BODY)])
    anilist.post_query("query { x }")
    assert anilist.DEFAULT_RETRY_AFTER_SECONDS in waits


def test_server_error_retries_with_backoff(monkeypatch, waits):
    error = fake_response(500, {"errors": [{"message": "Internal Server Error"}]})
    use_responses(monkeypatch, [error, error, fake_response(200, OK_BODY)])
    assert anilist.post_query("query { x }") == OK_BODY["data"]
    assert [w for w in waits if w in anilist.RETRY_WAITS_SECONDS] == [5, 15]


def test_server_error_gives_up_after_three_retries(monkeypatch, waits):
    error = fake_response(503)
    use_responses(monkeypatch, [error] * 4)
    with pytest.raises(anilist.AniListError, match="Giving up after 3 retries"):
        anilist.post_query("query { x }")


def test_graphql_error_is_raised_without_retry(monkeypatch, waits):
    use_responses(monkeypatch, [fake_response(404, {"errors": [{"message": "User not found"}]})])
    with pytest.raises(anilist.AniListError, match="User not found"):
        anilist.post_query("query { x }")


def test_offline_guard_blocks_real_network():
    with pytest.raises(RuntimeError, match="tried to use the network"):
        requests.get("https://graphql.anilist.co", timeout=5)
