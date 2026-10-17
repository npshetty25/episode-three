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
W1_MAX_UNION_DAYS = 40         # a batch's union window may not be wider than this; a longer w1 stands alone
TASK_REQUEST_CAP = 1100        # for the whole task, pilot included
STOP_RATIO_LIMIT = 1.15        # stop if actual / predicted records exceed this ...
STOP_MIN_BATCHES = 10          # ... once at least this many batches are done
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

def make_w1_batches(candidates, size=W1_BATCH_SIZE, max_union_days=W1_MAX_UNION_DAYS):
    """Group candidates into batches by w1 start.

    Shows are sorted by w1 start. A new batch starts when the current one has `size` shows OR
    adding the next show would make the batch's union window wider than `max_union_days`.
    Why the width cap: with releasing: true AniList returns a record for every AIRING day inside
    the union window, so a wide window downloads many rows we then trim away.
    A show whose own w1 window is longer than `max_union_days` stands alone, after the normal batches.
    """
    def start(doc):
        return (doc["trend_windows"]["w1"]["from"], doc["_id"])

    def width(doc_or_batch):
        batch = doc_or_batch if isinstance(doc_or_batch, list) else [doc_or_batch]
        return markers.window_days(union_window(batch))

    ordered = sorted(candidates, key=start)
    long_ones = [d for d in ordered if width(d) > max_union_days]
    batches, current = [], []
    for doc in (d for d in ordered if width(d) <= max_union_days):
        trial = current + [doc]
        if current and (len(trial) > size or width(trial) > max_union_days):
            batches.append(current)
            current = [doc]
        else:
            current = trial
    if current:
        batches.append(current)
    return batches + [[d] for d in long_ones]


def union_window(batch, key="w1"):
    """The window covering every show in the batch: [earliest start, latest end]."""
    windows = [d["trend_windows"][key] for d in batch]
    return {"from": min(w["from"] for w in windows), "to": max(w["to"] for w in windows)}


def estimate_batch_records(batch):
    """(lower, upper) record estimate for one batch: own-window days vs union-window days per show."""
    lower = sum(markers.window_days(d["trend_windows"]["w1"]) for d in batch)
    upper = len(batch) * markers.window_days(union_window(batch))
    return lower, upper


def airing_period(doc):
    """(first, last) day a show has releasing records: the day after episode 1 to the finale day."""
    ep1 = doc["markers"]["schedule"]["ep1"]
    first = (ep1 if ep1 is not None else doc["trend_windows"]["w1"]["from"] + DAY) + DAY
    w2 = doc["trend_windows"].get("w2")
    last = (w2["from"] + DAY) if w2 else doc["trend_windows"]["w1"]["to"]  # w2 starts one day before the finale
    return first, last


def overlap_days(from_a, to_a, from_b, to_b):
    """Number of days two windows share (both ends included); 0 if they do not overlap."""
    return max(0, (min(to_a, to_b) - max(from_a, from_b)).days + 1)


def predict_batch_records(batch):
    """Predict the raw records AniList returns for a batch (the airing-overlap model).

    With releasing: true, AniList returns one record per show per AIRING day inside the batch's
    union window, so for each show: union window overlap airing period. Checked against six real
    batches, it was within 6% of the real numbers.
    """
    union = union_window(batch)
    return sum(overlap_days(union["from"], union["to"], *airing_period(doc)) for doc in batch)


def predicted_requests(records):
    """Requests a batch needs for `records` rows: 50 per page, plus one extra empty page when the
    count is an exact multiple of 50 (a full page still says hasNextPage). Real batches matched this."""
    return records // 50 + 1


def should_stop(actual_total, predicted_total, batches_done):
    """Stop rule: after STOP_MIN_BATCHES batches, stop if actual / predicted exceeds STOP_RATIO_LIMIT.

    Returns (stop, ratio); ratio is None while there is nothing to compare.
    """
    if predicted_total <= 0:
        return False, None
    ratio = actual_total / predicted_total
    return batches_done >= STOP_MIN_BATCHES and ratio > STOP_RATIO_LIMIT, ratio


def is_binge(doc):
    """True for a show released all at once: start date equals end date, or M(1) equals M(final)."""
    start, end = markers.day_from_fuzzy(doc.get("start_date")), markers.day_from_fuzzy(doc.get("end_date"))
    if start is not None and start == end:
        return True
    schedule = doc["markers"]["schedule"]
    return schedule["ep1"] is not None and schedule["ep1"] == schedule["final"]


def make_w2_batches(candidates, size=W1_BATCH_SIZE, max_union_days=W1_MAX_UNION_DAYS):
    """Projection only (w2 is collected in a later task): batches by finale date, same size and width cap."""
    ordered = sorted(candidates, key=lambda d: (d["trend_windows"]["w2"]["from"], d["_id"]))
    batches, current = [], []
    for doc in ordered:
        trial = current + [doc]
        if current and (len(trial) > size or markers.window_days(union_window(trial, "w2")) > max_union_days):
            batches.append(current)
            current = [doc]
        else:
            current = trial
    if current:
        batches.append(current)
    return batches


def project_w2(candidates):
    """Projected w2 cost: (batches, records, requests).

    w2 has no releasing filter, so AniList returns a record for EVERY show-day of the union window
    (before the finale the records are releasing, after it they are not): records = shows x union days.
    """
    batches = make_w2_batches(candidates)
    records = [len(b) * markers.window_days(union_window(b, "w2")) for b in batches]
    return len(batches), sum(records), sum(predicted_requests(r) for r in records)


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
