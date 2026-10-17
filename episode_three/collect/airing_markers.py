"""Marker days M(n) and the per-show trend windows (TASK 008).

For each eligible candidate we find the days episodes 1-4 and the finale aired (from AniList's
airing schedule), and from them the date windows that TASK 009 will request trend data for.

Day convention: AniList stamps trend dates at 00:00 JST. Every marker day is stored the same
way, as a UTC datetime at 00:00 JST (JST day 2018-10-05 -> 2018-10-04T15:00:00Z), so markers and
trend dates compare directly and never mix time zones.
"""
import math
import statistics
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
DAY = timedelta(days=1)

BATCH_SIZE = 10            # shows per query; they share the same episode count N
FALLBACK_W1_DAYS = 35      # w1 fallback: [start - 1, start + 35]
W2_DAYS_AFTER_FINALE = 10  # w2: [finale - 1, finale + 10]
PENDING_DAYS = 9           # a show is pending until finale + 9 days <= today (JST)

# One batch: up to 10 shows that all have N episodes, asking only for episodes 1-4 and N.
# 10 shows x 5 episodes = at most 50 rows = one page. Only the filters used are passed.
MARKER_QUERY = """
query ($ids: [Int], $eps: [Int], $page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    airingSchedules(mediaId_in: $ids, episode_in: $eps, sort: [TIME]) { mediaId episode airingAt }
  }
}"""


# --- Days -------------------------------------------------------------------

def jst_day(airing_at_unix):
    """Unix seconds -> the UTC datetime of that JST calendar day's 00:00 JST.

    An airing at 00:30 JST belongs to that JST day; one at 23:30 JST also belongs to it.
    """
    jst = datetime.fromtimestamp(airing_at_unix, tz=JST)
    return datetime(jst.year, jst.month, jst.day, tzinfo=JST).astimezone(timezone.utc)


def day_from_fuzzy(fuzzy):
    """AniList FuzzyDate {year, month, day} -> the same day convention, or None if any part is missing."""
    if not fuzzy or any(fuzzy.get(part) is None for part in ("year", "month", "day")):
        return None
    try:
        return datetime(fuzzy["year"], fuzzy["month"], fuzzy["day"], tzinfo=JST).astimezone(timezone.utc)
    except ValueError:
        return None


# --- Batching ---------------------------------------------------------------

def _start_key(doc):
    start = doc.get("start_date") or {}
    return (start.get("year") or 0, start.get("month") or 0, start.get("day") or 0, doc["_id"])


def make_batches(candidates, size=BATCH_SIZE):
    """Group candidates by episode count N, then chunk each group into batches of <= `size`.

    Returns a list of (n_episodes, [docs]) in a stable order: by N, then by start date.
    Shows from different seasons can share a batch (there is no date window here).
    """
    groups = {}
    for doc in candidates:
        if doc.get("episodes"):
            groups.setdefault(doc["episodes"], []).append(doc)
    batches = []
    for n_episodes in sorted(groups):
        docs = sorted(groups[n_episodes], key=_start_key)
        for start in range(0, len(docs), size):
            batches.append((n_episodes, docs[start:start + size]))
    return batches


# --- Markers ----------------------------------------------------------------

def markers_from_schedule(rows, n_episodes):
    """{ep1..ep4, final: day or None} from one show's schedule rows, using the EARLIEST row per episode."""
    earliest = {}
    for row in rows:
        episode, at = row["episode"], row["airingAt"]
        if episode not in earliest or at < earliest[episode]:
            earliest[episode] = at
    markers = {f"ep{k}": jst_day(earliest[k]) if k in earliest else None for k in (1, 2, 3, 4)}
    markers["final"] = jst_day(earliest[n_episodes]) if n_episodes in earliest else None
    return markers


def marker_flags(markers):
    """Oddities to record (not to exclude on; final rules come in TASK 010)."""
    present = [markers[f"ep{k}"] for k in (1, 2, 3, 4) if markers[f"ep{k}"] is not None]
    return {
        "non_monotonic": any(a > b for a, b in zip(present, present[1:])),
        "multi_episode_premiere": markers["ep1"] is not None and markers["ep1"] == markers["ep2"],
        "ep4_same_day_as_ep3": markers["ep3"] is not None and markers["ep3"] == markers["ep4"],
        "finale_row_missing": markers["final"] is None,
    }


# --- Windows ----------------------------------------------------------------

def trend_windows(markers, start_date, end_date, today_jst):
    """The two date windows TASK 009 will request, how each was derived, and the collection status.

    Windows are padded by a day on purpose: TASK 009 trims exactly in Python, so we never depend
    on whether date_greater/date_lesser are inclusive.

    w1 (episodes 1-4): [M(1) - 1, M(4) + 1] when all of eps 1-4 are known; otherwise
        [start_date - 1, start_date + 35] (source "fallback_start_date"); no start day: no window.
    w2 (finale): [M(final) - 1, M(final) + 10]; otherwise the same from end_date
        (source "fallback_end_date").
    Status: "excluded" if a window cannot be built; "pending" if the finale + 9 days is still in the
    future; otherwise "ready".
    """
    early = [markers[f"ep{k}"] for k in (1, 2, 3, 4)]
    if all(day is not None for day in early):
        # min/max, not ep1/ep4 directly, so an out-of-order schedule still gives a valid window
        w1 = {"from": min(early) - DAY, "to": max(early) + DAY}
        source1 = "schedule"
    else:
        start = day_from_fuzzy(start_date)
        if start is not None:
            w1 = {"from": start - DAY, "to": start + FALLBACK_W1_DAYS * DAY}
            source1 = "fallback_start_date"
        else:
            w1, source1 = None, None

    if markers["final"] is not None:
        final_day, source2 = markers["final"], "schedule"
    else:
        final_day, source2 = day_from_fuzzy(end_date), "fallback_end_date"
    if final_day is not None:
        w2 = {"from": final_day - DAY, "to": final_day + W2_DAYS_AFTER_FINALE * DAY}
    else:
        w2, source2 = None, None

    reasons = []
    if w1 is None and w2 is None:
        reasons = ["markers_unavailable"]
    elif w1 is None:
        reasons = ["start_date_unknown"]
    elif w2 is None:
        reasons = ["end_date_unknown"]

    if reasons:
        status = "excluded"
    elif final_day + PENDING_DAYS * DAY > today_jst:
        status, reasons = "pending", ["finale_plus_9_days_not_reached"]
    else:
        status = "ready"
    return {"w1": w1, "w2": w2, "marker_source": {"w1": source1, "w2": source2},
            "collection_status": status, "reasons": reasons}


def candidate_update(doc, rows, n_episodes, today_jst, fetched_at):
    """The fields to $set on one candidate after its schedule rows are known."""
    markers = markers_from_schedule(rows, n_episodes)
    result = trend_windows(markers, doc.get("start_date"), doc.get("end_date"), today_jst)
    return {
        "markers": {"schedule": markers, "flags": marker_flags(markers)},
        "marker_source": result["marker_source"],
        "trend_windows": {"w1": result["w1"], "w2": result["w2"]},
        "collection_status": result["collection_status"],
        "collection_reasons": result["reasons"],
        "markers_fetched_at": fetched_at,
    }


def anilist_id(doc):
    return int(doc["_id"].split(":")[1])


def covers_every_pair(rows, ids, episodes):
    """True when `rows` contain every (show, episode) pair that was asked for.

    Each show has at most one schedule row per episode, so once every pair is present no more
    rows can exist, and a full page of exactly ids x episodes rows needs no second request.
    """
    seen = {(row["mediaId"], row["episode"]) for row in rows}
    return all((media_id, episode) in seen for media_id in ids for episode in episodes)


def group_rows_by_show(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["mediaId"], []).append(row)
    return grouped


# --- Estimating TASK 009's request count -------------------------------------

def window_days(window):
    """Number of days in a window, both ends included."""
    return (window["to"] - window["from"]).days + 1


def estimate_pages(docs, window_key, size=BATCH_SIZE, per_page=50):
    """Estimate the requests for one window type (w1 or w2) across `docs`.

    Shows are sorted by the start of their window and chunked into batches of `size`. For each
    batch the union window runs from the earliest start to the latest end.
    - upper bound: every show has one trend record per day of the UNION window.
    - lower bound: every show has one record per day of its OWN window.
    pages per batch = ceil(records / per_page), at least 1.
    """
    ordered = sorted(docs, key=lambda d: (d["trend_windows"][window_key]["from"], d["_id"]))
    batches = [ordered[i:i + size] for i in range(0, len(ordered), size)]
    upper = lower = records_upper = records_lower = 0
    for batch in batches:
        windows = [d["trend_windows"][window_key] for d in batch]
        union_days = window_days({"from": min(w["from"] for w in windows), "to": max(w["to"] for w in windows)})
        batch_upper, batch_lower = len(batch) * union_days, sum(window_days(w) for w in windows)
        records_upper, records_lower = records_upper + batch_upper, records_lower + batch_lower
        upper += max(1, math.ceil(batch_upper / per_page))
        lower += max(1, math.ceil(batch_lower / per_page))
    return {"batches": len(batches), "pages_upper": upper, "pages_lower": lower,
            "records_upper": records_upper, "records_lower": records_lower}


def length_distribution(lengths):
    """min / median / 95th percentile / max of a list of window lengths (days)."""
    ordered = sorted(lengths)
    if not ordered:
        return None
    p95 = ordered[round(0.95 * (len(ordered) - 1))]
    return {"min": ordered[0], "median": statistics.median(ordered), "p95": p95, "max": ordered[-1]}
