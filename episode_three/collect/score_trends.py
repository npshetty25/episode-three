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
STOP_MIN_BATCHES = 10          # ... once at least this many batches are done (w1)
W2_STOP_MIN_BATCHES = 5        # w2: the model is not yet validated on real batches, so check earlier
W2_CAP_CHOICES = (12, 14, 20, 40)  # union widths compared offline; the cheapest one is W2_MAX_UNION_DAYS
W2_MAX_UNION_DAYS = 14         # chosen from W2_CAP_CHOICES by predicted requests: 548 vs 666/568/638 (TASK 010 dry run)
W2_TASK_REQUEST_CAP = 800      # for the w2 task, including the 1-request probe
W2_PROBE_RESERVE = 1
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


# w2 = the finale window: WITHOUT the releasing filter, because the label needs the records after
# the finale (releasing: false) as well as the last releasing one.
TREND_QUERY_W2 = """
query ($ids: [Int], $from: Int, $to: Int, $page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    mediaTrends(mediaId_in: $ids, date_greater: $from, date_lesser: $to, sort: [MEDIA_ID, DATE]) {
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


def should_stop(actual_total, predicted_total, batches_done, min_batches=STOP_MIN_BATCHES):
    """Stop rule: after `min_batches` batches, stop if actual / predicted exceeds STOP_RATIO_LIMIT.

    Returns (stop, ratio); ratio is None while there is nothing to compare.
    """
    if predicted_total <= 0:
        return False, None
    ratio = actual_total / predicted_total
    return batches_done >= min_batches and ratio > STOP_RATIO_LIMIT, ratio


def is_binge(doc):
    """True for a show released all at once: start date equals end date, or M(1) equals M(final)."""
    start, end = markers.day_from_fuzzy(doc.get("start_date")), markers.day_from_fuzzy(doc.get("end_date"))
    if start is not None and start == end:
        return True
    schedule = doc["markers"]["schedule"]
    return schedule["ep1"] is not None and schedule["ep1"] == schedule["final"]


def make_w2_batches(candidates, size=W1_BATCH_SIZE, max_union_days=None):
    """Batches for the finale window: sorted by finale day (the w2 start), at most `size` shows each,
    and a union window no wider than `max_union_days` (default W2_MAX_UNION_DAYS)."""
    max_union_days = W2_MAX_UNION_DAYS if max_union_days is None else max_union_days
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


def predict_w2_batch_records(batch):
    """w2 has no releasing filter, so AniList returns one record per show per day of the union window."""
    return len(batch) * markers.window_days(union_window(batch, "w2"))


def w2_cap_comparison(candidates, caps=W2_CAP_CHOICES):
    """For each union-width cap: batches, predicted records and predicted requests (a list of dicts)."""
    rows = []
    for cap in caps:
        batches = make_w2_batches(candidates, max_union_days=cap)
        records = [predict_w2_batch_records(b) for b in batches]
        rows.append({"cap": cap, "batches": len(batches), "records": sum(records),
                     "requests": sum(predicted_requests(r) for r in records)})
    return rows


def choose_w2_cap(comparison):
    """The cap with the fewest predicted requests (the smaller cap wins a tie)."""
    return min(comparison, key=lambda row: (row["requests"], row["cap"]))["cap"]


def project_w2(candidates):
    """Projected w2 cost: (batches, records, requests) with the chosen cap."""
    batches = make_w2_batches(candidates)
    records = [predict_w2_batch_records(b) for b in batches]
    return len(batches), sum(records), sum(predicted_requests(r) for r in records)


# --- Fetching (the one place that talks to AniList) ---------------------------

def to_unix(moment):
    return int(moment.timestamp())


def fetch_trends(ids, window, before_request=None, query=TREND_QUERY):
    """All trend rows for a batch inside its union window, using the shared pagination helper."""
    return anilist.collect_pages(
        query, {"ids": ids, "from": to_unix(window["from"]), "to": to_unix(window["to"])},
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


def build_updates(doc, snapshots, collected_at, window="w1"):
    """What to write for one show and window: the score_trends fields and the candidate's status."""
    trimmed = trim_to_window(snapshots, doc["trend_windows"][window])
    trend_fields = {
        "season": doc.get("season"), "season_year": doc.get("season_year"),
        f"snapshots_{window}": trimmed, f"n_snapshots_{window}": len(trimmed), f"{window}_collected_at": collected_at,
    }
    candidate_fields = {f"{window}_status": "collected" if trimmed else "no_records",
                        f"{window}_collected_at": collected_at}
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


# --- Labels (w2 data is LABEL data: feature code must never read it) -----------------------------------

def _scored(snapshot):
    return (snapshot["average_score"] or 0) > 0


def find_primary_label(snapshots_w2):
    """The primary label: the last record with releasing = true and a score.

    Returns (score, date, episode) or None. This is the score on the finale's airing day.
    """
    releasing = [s for s in sorted(snapshots_w2, key=lambda s: s["date"]) if s["releasing"] and _scored(s)]
    if not releasing:
        return None
    last = releasing[-1]
    return last["average_score"], last["date"], last["episode"]


def find_secondary_label(snapshots_w2, finale_day):
    """The secondary (sensitivity) label: the scored record nearest to finale + 7 days, within finale + 5..9.

    Returns (score, date) or None. Ties go to the earlier day.
    """
    target = finale_day + 7 * DAY
    inside = [s for s in snapshots_w2 if _scored(s) and finale_day + 5 * DAY <= s["date"] <= finale_day + 9 * DAY]
    if not inside:
        return None
    best = min(inside, key=lambda s: (abs((s["date"] - target).days), s["date"]))
    return best["average_score"], best["date"]


def finale_flags(snapshots_w2, episodes):
    """Checks that the finale is where we think it is.

    - no_transition: no day where the records switch from releasing to not releasing inside the window.
    - finale_episode_mismatch: the last releasing record that carries an episode number has a number
      different from `episodes` (records without an episode number cannot be checked, so they are not flagged).
    - label_at_window_edge: the primary label's record is the first or the last record of the window,
      so the transition cannot be confirmed on both sides.
    """
    ordered = sorted(snapshots_w2, key=lambda s: s["date"])
    transition = any(a["releasing"] and not b["releasing"] for a, b in zip(ordered, ordered[1:]))
    with_episode = [s for s in ordered if s["releasing"] and s["episode"] is not None]
    mismatch = bool(with_episode) and with_episode[-1]["episode"] != episodes
    primary = find_primary_label(ordered)
    at_edge = primary is not None and primary[1] in (ordered[0]["date"], ordered[-1]["date"])
    return {"no_transition": not transition, "finale_episode_mismatch": mismatch, "label_at_window_edge": at_edge}


def marker_disagreement(snapshots_w1, schedule):
    """Episodes (1-4) whose trend marker and schedule marker differ by more than one day."""
    trend = trend_marker_days(snapshots_w1)
    return [n for n in (1, 2, 3, 4)
            if trend[n] is not None and schedule[f"ep{n}"] is not None
            and abs(day_difference(trend[n], schedule[f"ep{n}"])) > 1]
