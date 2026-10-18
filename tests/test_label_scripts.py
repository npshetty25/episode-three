"""Offline tests for the pure helpers inside scripts/check_labels.py and scripts/probe_trends_single.py."""
from datetime import datetime, timedelta, timezone

from episode_three.collect import score_trends as trends
from scripts import check_labels, probe_trends_single
from tests.conftest import load_fixture

UTC = timezone.utc
JST = timezone(timedelta(hours=9))
DAY = timedelta(days=1)
FINALE = datetime(2018, 12, 20, tzinfo=JST).astimezone(UTC)


def show(episodes=12):
    return {"_id": "anilist:10", "episodes": episodes,
            "trend_windows": {"w2": {"from": FINALE - DAY, "to": FINALE + 10 * DAY}}}


def test_analyse_finds_both_labels_and_no_flags_for_a_clean_show():
    rows = load_fixture("w2_rows_sample.json")["rows"]
    snapshots = trends.parse_trend_rows([r for r in rows if r["mediaId"] == 10])[0][10]
    result = check_labels.analyse(show(), snapshots)
    assert result["primary"][0] == 82 and result["secondary"][0] == 85
    assert not any(result["flags"].values())
    assert result["secondary"][0] - result["primary"][0] == 3


def test_analyse_flags_a_show_that_never_stops_releasing():
    rows = load_fixture("w2_rows_sample.json")["rows"]
    snapshots = trends.parse_trend_rows([r for r in rows if r["mediaId"] == 11])[0][11]
    result = check_labels.analyse(show(), snapshots)
    assert result["flags"]["no_transition"] is True
    assert result["secondary"][0] == 70  # a scored record exists at finale + 5..9: the flag, not the label, marks the oddity
    assert check_labels.analyse(show(), [])["primary"] is None


def test_probe_summary_describes_records_and_the_empty_case():
    unix = lambda day: int(datetime(2021, 1, day, tzinfo=JST).timestamp())
    rows = [{"mediaId": 5, "date": unix(12), "episode": None, "averageScore": 0, "popularity": 10, "releasing": True},
            {"mediaId": 5, "date": unix(13), "episode": 1, "averageScore": 71, "popularity": 11, "releasing": True},
            {"mediaId": 5, "date": unix(20), "episode": 2, "averageScore": 72, "popularity": 12, "releasing": False}]
    lines = probe_trends_single.describe(rows, has_next=True)
    assert "Records on the first page: 3 (more pages exist: True)" in lines[0]
    assert "2021-01-12" in lines[1] and "2021-01-20" in lines[1]
    assert "releasing true: 2, false: 1; scored records: 2" in lines[2] and "[1, 2]" in lines[3]
    assert probe_trends_single.describe([], False) == ["No trend records at all for this show."]
