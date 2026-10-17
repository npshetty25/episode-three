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


# --- shared pagination stop rule ---------------------------------------------

def fake_paged(rows_per_page, has_next):
    """A fake post_query serving the given pages; returns (fake, list_of_pages_requested)."""
    requested = []

    def fake(query, variables=None):
        requested.append(variables["page"])
        index = variables["page"] - 1
        return {"Page": {"pageInfo": {"hasNextPage": has_next[index]}, "items": rows_per_page[index]}}

    return fake, requested


def collect(per_page=3, **kwargs):
    return anilist.collect_pages("query", {}, lambda data: data["Page"]["items"], per_page, **kwargs)


def test_stops_when_has_next_page_is_false(monkeypatch):
    fake, requested = fake_paged([[1, 2, 3], [4, 5, 6]], [True, False])
    monkeypatch.setattr(anilist, "post_query", fake)
    assert collect() == [1, 2, 3, 4, 5, 6] and requested == [1, 2]


def test_stops_on_a_short_page_even_if_has_next_page_is_true(monkeypatch):
    fake, requested = fake_paged([[1, 2], [3]], [True, True])  # page 1 has 2 rows < perPage 3
    monkeypatch.setattr(anilist, "post_query", fake)
    assert collect() == [1, 2] and requested == [1]


def test_a_full_page_with_has_next_page_keeps_going(monkeypatch):
    fake, requested = fake_paged([[1, 2, 3], [4]], [True, True])
    monkeypatch.setattr(anilist, "post_query", fake)
    assert collect() == [1, 2, 3, 4] and requested == [1, 2]


def test_page_limit_and_budget_hook(monkeypatch):
    fake, requested = fake_paged([[1, 2, 3]] * 5, [True] * 5)
    monkeypatch.setattr(anilist, "post_query", fake)
    with pytest.raises(anilist.AniListError, match="more than 2 pages"):
        collect(max_pages=2)
    assert requested == [1, 2]

    calls = []

    def stop_before_second_request():
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("budget")

    requested.clear()
    with pytest.raises(RuntimeError, match="budget"):
        collect(before_request=stop_before_second_request)
    assert requested == [1]  # the hook ran before request 2, which was never made


def test_is_complete_skips_the_request_a_full_page_would_trigger(monkeypatch):
    fake, requested = fake_paged([[1, 2, 3], [4]], [True, False])  # a full page, hasNextPage true
    monkeypatch.setattr(anilist, "post_query", fake)
    assert collect(is_complete=lambda rows: len(rows) == 3) == [1, 2, 3] and requested == [1]
    requested.clear()  # when the rows do not yet cover everything, it still goes on
    assert collect(is_complete=lambda rows: len(rows) == 4) == [1, 2, 3, 4] and requested == [1, 2]
