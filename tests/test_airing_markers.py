"""Offline tests for episode_three/collect/airing_markers.py."""
from datetime import datetime, timedelta, timezone

from episode_three.collect import airing_markers as m

UTC = timezone.utc
JST = m.JST
DAY = timedelta(days=1)


def utc_day(year, month, day):
    """A marker day: 00:00 JST of that JST date, as a UTC datetime."""
    return datetime(year, month, day, tzinfo=JST).astimezone(UTC)


def unix(year, month, day, hour=0, minute=0):
    return int(datetime(year, month, day, hour, minute, tzinfo=JST).timestamp())


# --- days ---------------------------------------------------------------------

def test_jst_day_is_midnight_jst_stored_as_utc():
    assert m.jst_day(unix(2018, 10, 5, 12)) == datetime(2018, 10, 4, 15, 0, tzinfo=UTC)
    assert utc_day(2018, 10, 5) == datetime(2018, 10, 4, 15, 0, tzinfo=UTC)


def test_airings_just_after_and_just_before_midnight_jst_stay_on_their_jst_day():
    after_midnight = m.jst_day(unix(2018, 10, 5, 0, 30))   # 00:30 JST = 15:30 UTC the day before
    before_midnight = m.jst_day(unix(2018, 10, 5, 23, 30))  # 23:30 JST = 14:30 UTC the same day
    assert after_midnight == before_midnight == datetime(2018, 10, 4, 15, 0, tzinfo=UTC)
    assert m.jst_day(unix(2018, 10, 6, 0, 0)) == datetime(2018, 10, 5, 15, 0, tzinfo=UTC)  # next JST day


def test_fuzzy_dates_need_year_month_and_day():
    assert m.day_from_fuzzy({"year": 2018, "month": 10, "day": 5}) == datetime(2018, 10, 4, 15, tzinfo=UTC)
    assert m.day_from_fuzzy({"year": 2018, "month": 10, "day": None}) is None
    assert m.day_from_fuzzy(None) is None
    assert m.day_from_fuzzy({"year": 2018, "month": 2, "day": 31}) is None


# --- batching -----------------------------------------------------------------

def doc(number, episodes, year=2020, month=1, day=1):
    return {"_id": f"anilist:{number}", "episodes": episodes, "start_date": {"year": year, "month": month, "day": day}}


def test_batches_group_by_episode_count_in_chunks_of_at_most_10():
    docs = ([doc(n, 12) for n in range(1, 26)] + [doc(n, 13) for n in range(100, 103)] + [doc(200, 24)]
            + [{"_id": "anilist:999", "episodes": None}])
    batches = m.make_batches(docs)
    assert [(n, len(group)) for n, group in batches] == [(12, 10), (12, 10), (12, 5), (13, 3), (24, 1)]
    assert all(len({d["episodes"] for d in group}) == 1 for n, group in batches)
    assert sum(len(group) for n, group in batches) == 29  # the show without an episode count is left out


def test_batches_mix_seasons_and_are_ordered_by_start_date_and_stable():
    docs = [doc(3, 12, year=2022), doc(1, 12, year=2018), doc(2, 12, year=2020, month=4), doc(4, 12, year=2020, month=1)]
    (n, group), = m.make_batches(docs)
    assert [d["_id"] for d in group] == ["anilist:1", "anilist:4", "anilist:2", "anilist:3"]
    assert m.make_batches(docs) == m.make_batches(list(reversed(docs)))  # same result whatever the input order


def test_a_show_with_a_partial_start_date_still_batches():
    docs = [{"_id": "anilist:5", "episodes": 12, "start_date": None}, doc(6, 12)]
    assert len(m.make_batches(docs)[0][1]) == 2


# --- markers ------------------------------------------------------------------

def row(episode, at, media=1):
    return {"mediaId": media, "episode": episode, "airingAt": at}


def full_rows(n=12):
    """Weekly airings at 23:00 JST starting 2018-10-05, for episodes 1-4 and the finale n."""
    first = unix(2018, 10, 5, 23, 0)
    return [row(e, first + 7 * (e - 1) * 86_400) for e in (1, 2, 3, 4, n)]


def test_markers_use_the_earliest_row_for_each_episode():
    rows = [row(1, unix(2018, 10, 12)), row(1, unix(2018, 10, 5)), row(2, unix(2018, 10, 19))]  # ep 1 listed twice
    markers = m.markers_from_schedule(rows, 12)
    assert markers["ep1"] == utc_day(2018, 10, 5)
    assert markers["ep2"] == utc_day(2018, 10, 19)
    assert markers["ep3"] is None and markers["ep4"] is None and markers["final"] is None


def test_final_marker_comes_from_the_row_whose_episode_equals_the_episode_count():
    markers = m.markers_from_schedule(full_rows(12), 12)
    assert markers["final"] == utc_day(2018, 10, 5) + 77 * DAY  # episode 12 airs 11 weeks after episode 1
    assert markers["ep4"] == utc_day(2018, 10, 5) + 21 * DAY
    assert m.markers_from_schedule(full_rows(12), 13)["final"] is None  # no row for episode 13


# --- windows ------------------------------------------------------------------

TODAY = utc_day(2026, 10, 17)


def good_markers(first=(2018, 10, 5), final=(2018, 12, 21)):
    base = utc_day(*first)
    markers = {f"ep{k}": base + 7 * (k - 1) * DAY for k in (1, 2, 3, 4)}
    markers["final"] = utc_day(*final)
    return markers


def test_windows_from_the_schedule():
    markers = good_markers()
    result = m.trend_windows(markers, None, None, TODAY)
    assert result["w1"] == {"from": markers["ep1"] - DAY, "to": markers["ep4"] + DAY}
    assert result["w2"] == {"from": markers["final"] - DAY, "to": markers["final"] + 10 * DAY}
    assert result["marker_source"] == {"w1": "schedule", "w2": "schedule"}
    assert result["collection_status"] == "ready" and result["reasons"] == []


def test_w1_falls_back_to_the_start_date_when_an_early_episode_is_missing():
    markers = good_markers()
    markers["ep3"] = None
    start = {"year": 2018, "month": 10, "day": 5}
    result = m.trend_windows(markers, start, None, TODAY)
    assert result["w1"] == {"from": utc_day(2018, 10, 5) - DAY, "to": utc_day(2018, 10, 5) + 35 * DAY}
    assert result["marker_source"]["w1"] == "fallback_start_date" and result["collection_status"] == "ready"


def test_no_usable_start_day_means_no_w1_and_the_show_is_excluded():
    markers = good_markers()
    markers["ep2"] = None
    result = m.trend_windows(markers, {"year": 2018, "month": 10, "day": None}, None, TODAY)
    assert result["w1"] is None and result["marker_source"]["w1"] is None
    assert result["collection_status"] == "excluded" and result["reasons"] == ["start_date_unknown"]


def test_w2_falls_back_to_the_end_date():
    markers = good_markers()
    markers["final"] = None
    result = m.trend_windows(markers, None, {"year": 2018, "month": 12, "day": 21}, TODAY)
    assert result["w2"] == {"from": utc_day(2018, 12, 21) - DAY, "to": utc_day(2018, 12, 21) + 10 * DAY}
    assert result["marker_source"]["w2"] == "fallback_end_date" and result["collection_status"] == "ready"

    result = m.trend_windows(markers, None, None, TODAY)  # no end date either
    assert result["w2"] is None and result["reasons"] == ["end_date_unknown"]
    assert result["collection_status"] == "excluded"


def test_neither_window_means_markers_unavailable():
    nothing = {"ep1": None, "ep2": None, "ep3": None, "ep4": None, "final": None}
    result = m.trend_windows(nothing, None, None, TODAY)
    assert result["w1"] is None and result["w2"] is None
    assert result["collection_status"] == "excluded" and result["reasons"] == ["markers_unavailable"]


def test_pending_until_finale_plus_9_days_has_passed():
    markers = good_markers(final=(2026, 10, 1))
    assert m.trend_windows(markers, None, None, utc_day(2026, 10, 9))["collection_status"] == "pending"
    assert m.trend_windows(markers, None, None, utc_day(2026, 10, 9))["reasons"] == ["finale_plus_9_days_not_reached"]
    assert m.trend_windows(markers, None, None, utc_day(2026, 10, 10))["collection_status"] == "ready"  # exactly +9
    assert m.trend_windows(markers, None, None, utc_day(2026, 10, 17))["collection_status"] == "ready"


def test_pending_also_applies_to_an_end_date_fallback():
    markers = good_markers()
    markers["final"] = None
    result = m.trend_windows(markers, None, {"year": 2026, "month": 10, "day": 15}, TODAY)
    assert result["collection_status"] == "pending"


def test_an_out_of_order_schedule_still_gets_a_valid_window():
    markers = good_markers()
    markers["ep4"], markers["ep1"] = markers["ep1"], markers["ep4"]
    window = m.trend_windows(markers, None, None, TODAY)["w1"]
    assert window["from"] < window["to"]


# --- flags --------------------------------------------------------------------

def test_flags():
    clean = m.marker_flags(good_markers())
    assert clean == {"non_monotonic": False, "multi_episode_premiere": False,
                     "ep4_same_day_as_ep3": False, "finale_row_missing": False}

    out_of_order = good_markers()
    out_of_order["ep3"] = out_of_order["ep1"] - DAY
    assert m.marker_flags(out_of_order)["non_monotonic"] is True

    premiere = good_markers()
    premiere["ep2"] = premiere["ep1"]
    assert m.marker_flags(premiere)["multi_episode_premiere"] is True

    same_day = good_markers()
    same_day["ep4"] = same_day["ep3"]
    assert m.marker_flags(same_day)["ep4_same_day_as_ep3"] is True

    no_final = good_markers()
    no_final["final"] = None
    assert m.marker_flags(no_final)["finale_row_missing"] is True

    gap = good_markers()
    gap["ep2"] = None  # a missing episode alone is not "non_monotonic"
    assert m.marker_flags(gap)["non_monotonic"] is False


# --- one candidate's update ------------------------------------------------------

def test_candidate_update_has_the_documented_shape():
    fetched = datetime(2026, 10, 18, tzinfo=UTC)
    update = m.candidate_update(doc(1, 12), full_rows(12), 12, TODAY, fetched)
    assert set(update) == {"markers", "marker_source", "trend_windows", "collection_status",
                           "collection_reasons", "markers_fetched_at"}
    assert set(update["markers"]["schedule"]) == {"ep1", "ep2", "ep3", "ep4", "final"}
    assert set(update["markers"]["flags"]) == {"non_monotonic", "multi_episode_premiere",
                                               "ep4_same_day_as_ep3", "finale_row_missing"}
    assert update["markers_fetched_at"] == fetched and update["collection_status"] == "ready"
    assert "episode_in" in m.MARKER_QUERY and "notYetAired" not in m.MARKER_QUERY


# --- budget estimate ----------------------------------------------------------------

def windowed(number, start, days):
    return {"_id": f"anilist:{number}", "trend_windows": {"w1": {"from": start, "to": start + (days - 1) * DAY}}}


def test_window_days_and_length_distribution():
    assert m.window_days({"from": utc_day(2020, 1, 1), "to": utc_day(2020, 1, 1)}) == 1
    assert m.window_days({"from": utc_day(2020, 1, 1), "to": utc_day(2020, 1, 22)}) == 22
    assert m.length_distribution([]) is None
    assert m.length_distribution([22, 22, 24, 22, 36]) == {"min": 22, "median": 22, "p95": 36, "max": 36}


def test_estimate_pages_batches_by_window_start():
    base = utc_day(2020, 1, 1)
    docs = [windowed(n, base, 22) for n in range(10)]  # 10 identical windows: one batch
    one = m.estimate_pages(docs, "w1")
    assert one["batches"] == 1 and one["records_upper"] == one["records_lower"] == 220
    assert one["pages_upper"] == one["pages_lower"] == 5  # ceil(220 / 50)

    # a second batch whose members start months apart: union window is long, own windows are short
    spread = [windowed(100 + n, base + 60 * n * DAY, 22) for n in range(10)]
    two = m.estimate_pages(spread, "w1")
    assert two["pages_upper"] > two["pages_lower"] and two["batches"] == 1
    assert m.estimate_pages([], "w1")["batches"] == 0
