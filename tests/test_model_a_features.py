"""Offline tests for episode_three/features/model_a.py (snapshots, labels, features)."""
import inspect
import random
from datetime import datetime, timedelta, timezone

from episode_three.features import model_a as ma

UTC = timezone.utc
JST = timezone(timedelta(hours=9))
DAY = timedelta(days=1)


def day(month, d, year=2019):
    """00:00 JST of that date, as the stored UTC datetime."""
    return datetime(year, month, d, tzinfo=JST).astimezone(UTC)


def snap(date, score=70, popularity=5000, in_progress=100, episode=None, releasing=True):
    return {"date": date, "episode": episode, "average_score": score, "popularity": popularity,
            "in_progress": in_progress, "trending": 1, "releasing": releasing}


# --- final markers -------------------------------------------------------------------------------------

def test_final_marker_is_the_earliest_with_its_source():
    schedule = {"ep1": day(1, 3), "ep2": day(1, 10), "ep3": day(1, 17), "ep4": None}
    trend = {1: day(1, 3), 2: day(1, 9), 3: None, 4: day(1, 25)}
    m = ma.final_markers(schedule, trend)
    assert m[1] == {"day": day(1, 3), "source": "schedule"}   # a tie goes to the schedule
    assert m[2] == {"day": day(1, 9), "source": "trend"}      # the trend is earlier
    assert m[3] == {"day": day(1, 17), "source": "schedule"}
    assert m[4] == {"day": day(1, 25), "source": "trend"}
    assert ma.final_markers({}, {})[1] == {"day": None, "source": None}


# --- snapshot selection and the floor ------------------------------------------------------------------

def test_latest_scored_record_in_the_window_wins():
    m3, m4 = day(2, 1), day(2, 8)
    snaps = [snap(day(2, 4), 70), snap(day(2, 5), 71), snap(day(2, 6), 0), snap(day(2, 7), 72), snap(m4, 99)]
    chosen, reason = ma.select_snapshot(snaps, m3, m4)
    assert reason == "ok" and chosen["average_score"] == 72   # not M(4) itself, not the unscored day
    snaps = [snap(day(2, 5), 70), snap(day(2, 7), 0)]
    assert ma.select_snapshot(snaps, m3, m4)[0]["average_score"] == 70  # the unscored latest day is skipped


def test_the_window_never_includes_m_prev_or_earlier():
    """The floor: with M(3) and M(4) two days apart, only the day between them is allowed."""
    m3, m4 = day(2, 1), day(2, 3)
    snaps = [snap(m3, 60), snap(day(2, 2), 65), snap(day(1, 31), 50)]
    chosen, reason = ma.select_snapshot(snaps, m3, m4)
    assert chosen["average_score"] == 65 and ma.snapshot_window(m3, m4) == (day(2, 2), day(2, 2))
    # only the ep3 airing day itself has a score: it may contain ep3 reactions, so it is NOT usable
    assert ma.select_snapshot([snap(m3, 60)], m3, m4) == (None, "no_scored_record")


def test_one_day_apart_leaves_an_empty_window():
    m3, m4 = day(2, 1), day(2, 2)
    assert ma.snapshot_window(m3, m4) is None
    assert ma.select_snapshot([snap(m3, 60)], m3, m4) == (None, "empty_window")


def test_the_window_needs_m_prev_before_m_next():
    d = day(2, 1)
    assert ma.select_snapshot([snap(d)], d, d) == (None, "not_before")
    assert ma.select_snapshot([snap(d)], d + DAY, d) == (None, "not_before")
    assert ma.select_snapshot([snap(d)], None, d) == (None, "no_marker")
    assert ma.select_snapshot([snap(d)], d, None) == (None, "no_marker")


def test_a_wider_k_never_changes_an_existing_snapshot():
    """Latest wins: widening only reaches further back, so a show that has a snapshot keeps the same one."""
    rng = random.Random(7)
    base = day(3, 1)
    for _ in range(300):
        m_prev = base + rng.randint(0, 6) * DAY
        m_next = m_prev + rng.randint(1, 10) * DAY
        snaps = [snap(base + n * DAY, rng.choice([0, 0, 60, 70, 80])) for n in range(-2, 20)]
        small, _ = ma.select_snapshot(snaps, m_prev, m_next, k=3)
        wide, _ = ma.select_snapshot(snaps, m_prev, m_next, k=6)
        if small is not None:
            assert wide is small
        if wide is None:
            assert small is None


def test_floor_impact_counts_shrunk_and_lost_windows():
    m3, m4 = day(2, 1), day(2, 3)           # 2 days apart: floored window [2/2, 2/2], unfloored [1/31, 2/2]
    only_old = [snap(day(1, 31), 55)]
    assert ma.floor_impact(only_old, m3, m4) == {"shrunk": True, "lost": True}
    has_new = only_old + [snap(day(2, 2), 60)]
    assert ma.floor_impact(has_new, m3, m4) == {"shrunk": True, "lost": False}
    wide = day(2, 10)                        # a week apart: the floor changes nothing
    assert ma.floor_impact(only_old, m3, wide) == {"shrunk": False, "lost": False}
    assert ma.floor_impact(only_old, m3, m3) == {"shrunk": False, "lost": False}


def test_popularity_and_in_progress_come_from_the_same_record():
    m3, m4 = day(2, 1), day(2, 8)
    snaps = [snap(day(2, 6), 70, popularity=111, in_progress=7), snap(day(2, 7), 71, popularity=222, in_progress=9)]
    values = ma.snapshot_values(ma.select_snapshot(snaps, m3, m4)[0])
    assert (values["score"], values["popularity"], values["in_progress"]) == (71, 222, 9)


# --- labels --------------------------------------------------------------------------------------------

def test_primary_label_and_offset():
    finale = day(4, 10)
    snaps = [snap(finale, 80, episode=12), snap(finale + DAY, 82, releasing=False)]
    label = ma.primary_label(snaps, finale)
    assert (label["score"], label["offset_days"], label["offset_unusual"]) == (80, 0, False)
    late = [snap(finale, 80), snap(finale + DAY, 81)]
    assert ma.primary_label(late, finale)["offset_days"] == 1 and not ma.primary_label(late, finale)["offset_unusual"]
    early = [snap(finale - DAY, 79)]
    assert ma.primary_label(early, finale)["offset_days"] == -1 and not ma.primary_label(early, finale)["offset_unusual"]
    for offset in (-2, 2, 9):   # more than one day either side is unusual
        far = ma.primary_label([snap(finale + offset * DAY, 79)], finale)
        assert far["offset_days"] == offset and far["offset_unusual"] is True
    assert ma.primary_label([snap(finale, 0)], finale) is None
    assert ma.primary_label([], finale) is None
