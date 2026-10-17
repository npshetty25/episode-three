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


# --- the 40-day union cap -------------------------------------------------------------

def test_a_batch_closes_when_the_next_show_would_widen_the_union_past_40_days():
    base = utc_day(2018, 10, 1)
    # 24-day windows starting every 8 days: two shows span 32 days, three would span 40 days + ... check the cap
    docs = [candidate(n, base + 8 * n * DAY, 24) for n in range(6)]
    batches = trends.make_w1_batches(docs)
    for batch in batches:
        assert markers.window_days(trends.union_window(batch)) <= trends.W1_MAX_UNION_DAYS
    assert [len(b) for b in batches] == [3, 3]  # 3 shows span 8+8+24 = 40 days; a 4th would make 48
    assert trends.W1_MAX_UNION_DAYS == 40


def test_size_still_caps_a_batch_at_10_when_the_union_is_narrow():
    base = utc_day(2018, 10, 1)
    docs = [candidate(n, base, 24) for n in range(23)]  # identical windows: width never grows
    assert [len(b) for b in trends.make_w1_batches(docs)] == [10, 10, 3]


def test_long_windows_stay_alone_and_order_is_stable_with_the_cap():
    base = utc_day(2018, 10, 1)
    docs = [candidate(n, base + 5 * n * DAY, 24) for n in range(8)] + [candidate(90, base, 60), candidate(91, base, 41)]
    batches = trends.make_w1_batches(docs)
    assert [b[0]["_id"] for b in batches[-2:]] == ["anilist:90", "anilist:91"] and all(len(b) == 1 for b in batches[-2:])
    assert trends.make_w1_batches(docs) == trends.make_w1_batches(list(reversed(docs)))
    flat = [d["trend_windows"]["w1"]["from"] for b in batches[:-2] for d in b]
    assert flat == sorted(flat)


# --- the airing-overlap model, checked against six real batches ------------------------

def pilot_batches():
    fixture = load_fixture("trend_pilot_batches.json")
    parse = lambda text: None if text is None else datetime.fromisoformat(text)
    batches = []
    for entry in fixture["batches"]:
        shows = [{"_id": s["_id"],
                  "trend_windows": {"w1": {"from": parse(s["w1"]["from"]), "to": parse(s["w1"]["to"])},
                                    "w2": {"from": parse(s["w2_from"]), "to": parse(s["w2_from"])}},
                  "markers": {"schedule": {"ep1": parse(s["ep1"])}}} for s in entry["shows"]]
        batches.append((shows, entry["actual_records"]))
    return batches


def test_the_model_matches_each_of_the_six_real_batches_within_10_percent():
    batches = pilot_batches()
    assert len(batches) == 6
    for shows, actual in batches:
        predicted = trends.predict_batch_records(shows)
        assert abs(predicted - actual) / actual <= 0.10, (predicted, actual)
    total_predicted = sum(trends.predict_batch_records(shows) for shows, _ in batches)
    assert abs(total_predicted - 1771 - 336) / (1771 + 336) <= 0.05  # all six together


def test_predicted_requests_match_the_real_request_counts():
    # real batches: (records returned, requests used): 336 -> 7, 217 -> 5, 339 -> 7, 550 -> 12, 350 -> 8, 315 -> 7
    for records, requests_used in [(336, 7), (217, 5), (339, 7), (550, 12), (350, 8), (315, 7)]:
        assert trends.predicted_requests(records) == requests_used
    assert trends.predicted_requests(0) == 1


def test_airing_period_runs_from_the_day_after_episode_1_to_the_finale_day():
    base = utc_day(2018, 10, 5)
    doc = {"trend_windows": {"w1": {"from": base - DAY, "to": base + 30 * DAY},
                             "w2": {"from": base + 76 * DAY, "to": base + 87 * DAY}},
           "markers": {"schedule": {"ep1": base}}}
    assert trends.airing_period(doc) == (base + DAY, base + 77 * DAY)
    doc["markers"]["schedule"]["ep1"] = None  # fallback: w1 starts one day before the start date
    assert trends.airing_period(doc)[0] == base + DAY
    assert trends.overlap_days(base, base + 9 * DAY, base + 5 * DAY, base + 20 * DAY) == 5
    assert trends.overlap_days(base, base + 2 * DAY, base + 5 * DAY, base + 6 * DAY) == 0


# --- the model-based stop rule ---------------------------------------------------------------

def test_stop_rule_waits_for_ten_batches_then_stops_above_1_15():
    assert trends.STOP_RATIO_LIMIT == 1.15 and trends.STOP_MIN_BATCHES == 10
    assert trends.should_stop(2000, 1000, 9) == (False, 2.0)   # far over, but fewer than 10 batches
    assert trends.should_stop(1160, 1000, 10) == (True, 1.16)
    assert trends.should_stop(1150, 1000, 10) == (False, 1.15)  # exactly 1.15 is allowed
    assert trends.should_stop(900, 1000, 50) == (False, 0.9)
    assert trends.should_stop(5, 0, 50) == (False, None)


# --- binge releases ------------------------------------------------------------------------------

def test_binge_means_start_equals_end_or_the_first_and_last_marker_coincide():
    base = utc_day(2018, 10, 18)
    full = {"year": 2018, "month": 10, "day": 18}
    nothing = {"ep1": None, "final": None}
    assert trends.is_binge({"start_date": full, "end_date": dict(full), "markers": {"schedule": nothing}}) is True
    assert trends.is_binge({"start_date": full, "end_date": {"year": 2018, "month": 12, "day": 20},
                            "markers": {"schedule": {"ep1": base, "final": base + 70 * DAY}}}) is False
    assert trends.is_binge({"start_date": None, "end_date": None,
                            "markers": {"schedule": {"ep1": base, "final": base}}}) is True
    assert trends.is_binge({"start_date": {"year": 2018, "month": 10, "day": None},
                            "end_date": {"year": 2018, "month": 10, "day": None},
                            "markers": {"schedule": nothing}}) is False  # partial dates prove nothing


# --- the w2 projection ------------------------------------------------------------------------------

def finale_doc(number, finale_day):
    return {"_id": f"anilist:{number}",
            "trend_windows": {"w2": {"from": finale_day - DAY, "to": finale_day + 10 * DAY}}}


def test_w2_projection_batches_by_finale_date_with_no_releasing_filter():
    base = utc_day(2019, 1, 1)
    docs = [finale_doc(n, base + n * DAY) for n in range(10)]  # finales on 10 consecutive days
    batches, records, requests_needed = trends.project_w2(docs)
    assert batches == 1
    assert records == 10 * 21  # union = [base-1, base+9+10]: 21 days, every day has a record for every show
    assert requests_needed == 210 // 50 + 1
    far_apart = docs + [finale_doc(99, base + 200 * DAY)]
    assert trends.project_w2(far_apart)[0] == 2  # a finale 200 days later cannot join the batch (width cap)
    assert trends.project_w2([]) == (0, 0, 0)
