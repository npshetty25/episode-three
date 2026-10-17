"""Offline tests for episode_three/collect/score_trends.py."""
from datetime import datetime, timedelta, timezone

import pytest

from episode_three.clients import anilist
from episode_three.collect import airing_markers as markers
from episode_three.collect import score_trends as trends
from tests.conftest import load_fixture

UTC = timezone.utc
JST = markers.JST
DAY = timedelta(days=1)


def utc_day(year, month, day):
    return datetime(year, month, day, tzinfo=JST).astimezone(UTC)


def candidate(number, start, days):
    """A candidate with a w1 window of `days` days beginning at `start`."""
    return {"_id": f"anilist:{number}", "season": "FALL", "season_year": 2018,
            "trend_windows": {"w1": {"from": start, "to": start + (days - 1) * DAY}}}


# --- batching -----------------------------------------------------------------

def test_batches_are_sorted_by_start_in_tens_and_long_windows_stand_alone():
    base = utc_day(2018, 10, 1)
    docs = [candidate(n, base + (24 - n) * DAY, 24) for n in range(24)]  # shuffled-by-construction order
    docs.append(candidate(100, base + 3 * DAY, 108))                      # a long window
    docs.append(candidate(101, base + 9 * DAY, 41))                       # also over the limit
    batches = trends.make_w1_batches(docs)
    assert [len(b) for b in batches] == [10, 10, 4, 1, 1]
    flat = [d["_id"] for b in batches[:3] for d in b]
    starts = [d["trend_windows"]["w1"]["from"] for b in batches[:3] for d in b]
    assert starts == sorted(starts) and len(flat) == 24
    assert [b[0]["_id"] for b in batches[3:]] == ["anilist:100", "anilist:101"]  # long ones, in start order
    assert trends.make_w1_batches(docs) == trends.make_w1_batches(list(reversed(docs)))  # stable


def test_a_window_of_exactly_40_days_is_not_long():
    base = utc_day(2018, 10, 1)
    assert [len(b) for b in trends.make_w1_batches([candidate(1, base, 40), candidate(2, base, 41)])] == [1, 1]
    assert [len(b) for b in trends.make_w1_batches([candidate(1, base, 40), candidate(2, base, 40)])] == [2]


def test_union_window_and_record_estimates():
    base = utc_day(2018, 10, 1)
    batch = [candidate(1, base, 10), candidate(2, base + 5 * DAY, 10)]
    assert trends.union_window(batch) == {"from": base, "to": base + 14 * DAY}
    assert trends.estimate_batch_records(batch) == (20, 30)  # own days 10 + 10; union 15 days x 2 shows


# --- parsing ------------------------------------------------------------------

def all_rows():
    pages = load_fixture("trend_pages_sample.json")["pages"]
    return [row for page in pages for row in page["Page"]["mediaTrends"]]


def test_parse_removes_page_boundary_repeats_and_counts_them():
    by_show, duplicates = trends.parse_trend_rows(all_rows())
    assert duplicates == 1
    assert sorted(by_show) == [1, 2]
    assert [s["average_score"] for s in by_show[1]] == [0, 78] and [s["average_score"] for s in by_show[2]] == [0, 70]
    first = by_show[2][0]
    assert first == {"date": datetime(2018, 10, 2, 15, 0, tzinfo=UTC), "episode": None, "average_score": 0,
                     "popularity": 900, "in_progress": 8, "trending": 4, "releasing": True}
    assert first["date"] == utc_day(2018, 10, 3)  # stored date = 00:00 JST


def test_a_tie_across_shows_on_the_same_date_keeps_both_rows():
    by_show, _ = trends.parse_trend_rows(all_rows())
    assert by_show[1][0]["date"] == by_show[2][0]["date"]  # same day, different shows: neither is dropped


def test_snapshots_are_sorted_by_date_whatever_the_row_order():
    rows = list(reversed(all_rows()))
    by_show, _ = trends.parse_trend_rows(rows)
    assert [s["date"] for s in by_show[1]] == sorted(s["date"] for s in by_show[1])


def test_trim_keeps_only_the_shows_own_window():
    by_show, _ = trends.parse_trend_rows(all_rows())
    window = {"from": utc_day(2018, 10, 4), "to": utc_day(2018, 10, 4)}  # only the second day
    assert [s["average_score"] for s in trends.trim_to_window(by_show[1], window)] == [78]
    assert trends.trim_to_window(by_show[1], {"from": utc_day(2019, 1, 1), "to": utc_day(2019, 1, 2)}) == []


# --- fetching two pages with a tie ------------------------------------------------

def test_fetch_follows_two_pages_with_the_documented_variables(monkeypatch):
    pages = load_fixture("trend_pages_sample.json")["pages"]
    seen = []

    def fake(query, variables=None):
        seen.append(variables)
        return pages[variables["page"] - 1]

    monkeypatch.setattr(anilist, "post_query", fake)
    window = {"from": utc_day(2018, 10, 3), "to": utc_day(2018, 10, 20)}
    rows = anilist.collect_pages(trends.TREND_QUERY, {"ids": [1, 2], "from": trends.to_unix(window["from"]),
                                                    "to": trends.to_unix(window["to"])},
                                 lambda data: data["Page"]["mediaTrends"], 3)  # page size 3: both pages are full
    assert len(rows) == 5 and [v["page"] for v in seen] == [1, 2]
    assert set(seen[0]) == {"ids", "from", "to", "page"} and all(isinstance(seen[0][k], int) for k in ("from", "to"))
    assert "sort: [MEDIA_ID, DATE]" in trends.TREND_QUERY and "releasing: true" in trends.TREND_QUERY
    assert "date_greater: $from" in trends.TREND_QUERY and "date_lesser: $to" in trends.TREND_QUERY
    by_show, duplicates = trends.parse_trend_rows(rows)
    assert duplicates == 1 and sum(len(v) for v in by_show.values()) == 4


# --- what gets written ----------------------------------------------------------------

def test_updates_are_the_same_for_the_same_input_and_statuses_follow_the_records():
    by_show, _ = trends.parse_trend_rows(all_rows())
    doc = candidate(1, utc_day(2018, 10, 3), 5)
    stamp = datetime(2026, 10, 18, tzinfo=UTC)
    first = trends.build_updates(doc, by_show[1], stamp)
    again = trends.build_updates(doc, by_show[1], stamp)
    assert first == again  # a re-write of the same input changes nothing
    trend_fields, candidate_fields = first
    assert trend_fields["n_snapshots_w1"] == 2 == len(trend_fields["snapshots_w1"])
    assert trend_fields["season"] == "FALL" and trend_fields["w1_collected_at"] == stamp
    assert candidate_fields == {"w1_status": "collected", "w1_collected_at": stamp}

    empty_fields, empty_candidate = trends.build_updates(doc, [], stamp)
    assert empty_fields["n_snapshots_w1"] == 0 and empty_candidate["w1_status"] == "no_records"


# --- trend markers vs schedule markers --------------------------------------------------

def snap(day, episode=None, score=80, releasing=True):
    return {"date": day, "episode": episode, "average_score": score, "popularity": 1, "in_progress": 1,
            "trending": 1, "releasing": releasing}


def test_trend_marker_is_the_first_record_with_that_episode():
    base = utc_day(2018, 10, 5)
    snaps = [snap(base + 8 * DAY, 2), snap(base, 1), snap(base + 1 * DAY, 1), snap(base + 15 * DAY, 3)]
    days = trends.trend_marker_days(snaps)
    assert days == {1: base, 2: base + 8 * DAY, 3: base + 15 * DAY, 4: None}


def test_day_difference_and_earliest():
    base = utc_day(2018, 10, 5)
    assert trends.day_difference(base + DAY, base) == 1 and trends.day_difference(base - DAY, base) == -1
    assert trends.day_difference(base, base) == 0
    assert trends.earliest(None, base + DAY, base) == base and trends.earliest(None, None) is None


def test_ep3_snapshot_check_covers_each_reason():
    m3, m4 = utc_day(2018, 10, 19), utc_day(2018, 10, 26)
    good = [snap(m4 - DAY, score=82)]
    assert trends.ep3_snapshot_check(good, m3, m4) == (True, "ok")
    assert trends.ep3_snapshot_check(good, m3, None) == (False, "no_m4")
    assert trends.ep3_snapshot_check(good, None, m4) == (False, "no_m3")
    assert trends.ep3_snapshot_check(good, m4, m4) == (False, "m3_not_before_m4")
    assert trends.ep3_snapshot_check([snap(m4 - DAY, score=0)], m3, m4) == (False, "no_scored_record")      # score 0
    assert trends.ep3_snapshot_check([snap(m4 - 4 * DAY)], m3, m4) == (False, "no_scored_record")           # too early
    assert trends.ep3_snapshot_check([snap(m4, score=80)], m3, m4) == (False, "no_scored_record")           # on M(4)
    assert trends.ep3_snapshot_check([snap(m4 - 3 * DAY, score=80)], m3, m4) == (True, "ok")                # window edge
    assert trends.ep3_snapshot_check([snap(m4 - DAY, releasing=False)], m3, m4) == (False, "no_scored_record")
