"""Collect the daily score trends for window 1 (premiere -> episode 4) (TASK 009).

Model A's features come from these daily records: the episode-1 and episode-3 snapshots, their
popularity, and the trend episode markers. Everything here is a pure function except
fetch_trends(), the one place that talks to AniList.

Rules that matter:
- Sort [MEDIA_ID, DATE]. Sorting by DATE alone leaves ties between the 10 shows of a batch on the
  same day, and an unstable tie order can skip or repeat rows across pages. We also dedupe on
  (mediaId, date) and count the duplicates.
- Windows are padded by a day on purpose (TASK 008). We trim to each show's own window in Python,
  so nothing depends on whether date_greater/date_lesser are inclusive.
- A batch is written only after ALL its pages arrived, so a crash never leaves half a show's
  history in the database.
"""
from datetime import datetime, timedelta, timezone

from episode_three.clients import anilist
from episode_three.collect import airing_markers as markers

COLLECTION = "score_trends"
JOB = "score_trends_w1"

W1_BATCH_SIZE = 10
LONG_WINDOW_DAYS = 40          # a w1 window longer than this gets a batch of its own
TASK_REQUEST_CAP = 1100        # for the whole task, pilot included
PILOT_RATIO_LIMIT = 1.3        # stop if records per batch exceed 1.3x the estimate
MAX_PAGES = 30
DAY = timedelta(days=1)

# Only these filters are passed (null filters make AniList fail).
TREND_QUERY = """
query ($ids: [Int], $from: Int, $to: Int, $page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    mediaTrends(mediaId_in: $ids, date_greater: $from, date_lesser: $to, releasing: true,
                sort: [MEDIA_ID, DATE]) {
      mediaId date episode averageScore popularity inProgress trending releasing
    }
  }
}"""


# --- Batching ----------------------------------------------------------------

def make_w1_batches(candidates, size=W1_BATCH_SIZE):
    """Group candidates into batches by w1 start: sorted, chunks of `size`, long windows alone.

    Returns a list of lists of candidate docs. Normal batches come first (in start order), then
    one batch per show whose w1 is longer than LONG_WINDOW_DAYS, so a long window cannot
    stretch the union window of ten other shows.
    """
    def start(doc):
        return (doc["trend_windows"]["w1"]["from"], doc["_id"])

    ordered = sorted(candidates, key=start)
    normal = [d for d in ordered if markers.window_days(d["trend_windows"]["w1"]) <= LONG_WINDOW_DAYS]
    long_ones = [d for d in ordered if markers.window_days(d["trend_windows"]["w1"]) > LONG_WINDOW_DAYS]
    batches = [normal[i:i + size] for i in range(0, len(normal), size)]
    return batches + [[d] for d in long_ones]


def union_window(batch):
    """The window covering every show in the batch: [earliest start, latest end]."""
    windows = [d["trend_windows"]["w1"] for d in batch]
    return {"from": min(w["from"] for w in windows), "to": max(w["to"] for w in windows)}


def estimate_batch_records(batch):
    """(lower, upper) record estimate for one batch: own-window days vs union-window days per show."""
    lower = sum(markers.window_days(d["trend_windows"]["w1"]) for d in batch)
    upper = len(batch) * markers.window_days(union_window(batch))
    return lower, upper


# --- Fetching (the one place that talks to AniList) ---------------------------

def to_unix(moment):
    return int(moment.timestamp())


def fetch_trends(ids, window, before_request=None):
    """All trend rows for a batch inside its union window, using the shared pagination helper."""
    return anilist.collect_pages(
        TREND_QUERY, {"ids": ids, "from": to_unix(window["from"]), "to": to_unix(window["to"])},
        lambda data: data["Page"]["mediaTrends"], 50, max_pages=MAX_PAGES, before_request=before_request)


# --- Parsing and trimming ------------------------------------------------------

def parse_trend_rows(rows):
    """Group raw rows into snapshots per show. Returns ({media_id: [snapshots by date]}, duplicates).

    A snapshot's date is the stored BSON UTC datetime, which is 00:00 JST of that day. Rows
    repeated for the same (mediaId, date) are dropped and counted.
    """
    seen = set()
    duplicates = 0
    by_show = {}
    for row in rows:
        key = (row["mediaId"], row["date"])
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        by_show.setdefault(row["mediaId"], []).append({
            "date": datetime.fromtimestamp(row["date"], tz=timezone.utc),
            "episode": row["episode"],
            "average_score": row["averageScore"],
            "popularity": row["popularity"],
            "in_progress": row["inProgress"],
            "trending": row["trending"],
            "releasing": row["releasing"],
        })
    for snapshots in by_show.values():
        snapshots.sort(key=lambda s: s["date"])
    return by_show, duplicates


def trim_to_window(snapshots, window):
    """Keep only the snapshots inside the show's own window (both ends included)."""
    return [s for s in snapshots if window["from"] <= s["date"] <= window["to"]]


def build_updates(doc, snapshots, collected_at):
    """What to write for one show: the score_trends fields and the candidate's w1 status."""
    trimmed = trim_to_window(snapshots, doc["trend_windows"]["w1"])
    trend_fields = {
        "season": doc.get("season"), "season_year": doc.get("season_year"),
        "snapshots_w1": trimmed, "n_snapshots_w1": len(trimmed), "w1_collected_at": collected_at,
    }
    candidate_fields = {"w1_status": "collected" if trimmed else "no_records", "w1_collected_at": collected_at}
    return trend_fields, candidate_fields


# --- Comparing trend markers with schedule markers ------------------------------

def trend_marker_days(snapshots):
    """{n: day of the first snapshot with episode == n, or None} for n = 1..4."""
    days = {n: None for n in (1, 2, 3, 4)}
    for snapshot in sorted(snapshots, key=lambda s: s["date"]):
        episode = snapshot["episode"]
        if episode in days and days[episode] is None:
            days[episode] = snapshot["date"]
    return days


def day_difference(trend_day, schedule_day):
    """Trend marker minus schedule marker, in whole days (both are 00:00-JST datetimes)."""
    return round((trend_day - schedule_day).total_seconds() / 86_400)


def earliest(*days):
    """The earliest of the given days, ignoring None (None if all are None). This is M(n)."""
    known = [d for d in days if d is not None]
    return min(known) if known else None


def ep3_snapshot_check(snapshots, m3, m4):
    """Can this show give an episode-3 snapshot? Returns (ok, reason).

    Rule (spec section 7): the latest scored releasing record in [M(4) - 3, M(4) - 1], and M(3) < M(4).
    reason is "ok", "no_m4", "no_m3", "m3_not_before_m4" or "no_scored_record".
    """
    if m4 is None:
        return False, "no_m4"
    if m3 is None:
        return False, "no_m3"
    if not m3 < m4:
        return False, "m3_not_before_m4"
    scored = [s for s in snapshots if s["releasing"] and (s["average_score"] or 0) > 0
              and m4 - 3 * DAY <= s["date"] <= m4 - DAY]
    return (True, "ok") if scored else (False, "no_scored_record")
