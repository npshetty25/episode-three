"""Model A features, labels and the exclusion ledger. Pure functions: no database, no network.

Leakage rule: everything in the FEATURES section sees window-1 data (snapshots_w1) and the schedule only.
Window-2 data (snapshots_w2) is LABEL data and appears only in the LABELS section and in build_all, which
passes it to the label functions and nowhere else. tests/test_model_a_features.py asserts this.
"""
import statistics
from datetime import timedelta

from episode_three.collect import score_trends as trends

DAY = timedelta(days=1)
K = 3                       # how many days before M(next) a snapshot may be taken (TASK 011 ruling)
POPULARITY_MIN = 2000       # the real popularity filter, applied to the ep3 snapshot (spec section 6)
SEASON_ORDER = ("WINTER", "SPRING", "SUMMER", "FALL")
PREQUEL_FORMATS = ("TV", "ONA", "TV_SHORT", "MOVIE")
TRAIN_LAST_YEAR, VALIDATION_YEAR = 2023, 2024   # train <= 2023, validation 2024, test 2025 -> Summer 2026


# --- FEATURES: window-1 data and the schedule only --------------------------------------------------

def trend_markers(snapshots_w1):
    """{n: day of the first snapshot with episode == n, or None} for n = 1..4."""
    return trends.trend_marker_days(snapshots_w1)


def final_markers(schedule, trend):
    """M(n) for n = 1..4: the earliest of the schedule day and the trend day.

    Returns {n: {"day": datetime or None, "source": "schedule" | "trend" | None}}. On a tie the schedule wins.
    """
    result = {}
    for n in (1, 2, 3, 4):
        s, t = schedule.get(f"ep{n}"), trend.get(n)
        if s is None and t is None:
            result[n] = {"day": None, "source": None}
        elif t is None or (s is not None and s <= t):
            result[n] = {"day": s, "source": "schedule"}
        else:
            result[n] = {"day": t, "source": "trend"}
    return result


def snapshot_window(m_prev, m_next, k=K):
    """The floored window [max(m_prev + 1, m_next - k), m_next - 1], or None if it is empty or invalid."""
    if m_prev is None or m_next is None or not m_prev < m_next:
        return None
    low, high = max(m_prev + DAY, m_next - k * DAY), m_next - DAY
    return (low, high) if low <= high else None


def _latest_scored(snapshots, low, high):
    scored = [s for s in snapshots if (s["average_score"] or 0) > 0 and low <= s["date"] <= high]
    return max(scored, key=lambda s: s["date"]) if scored else None


def select_snapshot(snapshots_w1, m_prev, m_next, k=K):
    """The latest record with average_score > 0 in [max(m_prev + 1, m_next - k), m_next - 1].

    Returns (snapshot or None, reason). reason: ok | no_marker | not_before | empty_window | no_scored_record.
    Used for ep3 (M(3), M(4)) and ep1 (M(1), M(2)). Only window-1 data goes in.
    """
    if m_prev is None or m_next is None:
        return None, "no_marker"
    if not m_prev < m_next:
        return None, "not_before"
    window = snapshot_window(m_prev, m_next, k)
    if window is None:
        return None, "empty_window"
    snapshot = _latest_scored(snapshots_w1, *window)
    return (snapshot, "ok") if snapshot else (None, "no_scored_record")


def floor_impact(snapshots_w1, m_prev, m_next, k=K):
    """Did the M(prev) + 1 floor change this window, and did it cost the show its snapshot?

    shrunk: the floored window is narrower than [m_next - k, m_next - 1].
    lost:   the unfloored window had a scored record, the floored one has none.
    """
    if m_prev is None or m_next is None or not m_prev < m_next:
        return {"shrunk": False, "lost": False}
    shrunk = m_prev + DAY > m_next - k * DAY
    unfloored = _latest_scored(snapshots_w1, m_next - k * DAY, m_next - DAY)
    floored, _ = select_snapshot(snapshots_w1, m_prev, m_next, k)
    return {"shrunk": shrunk, "lost": unfloored is not None and floored is None}


def snapshot_values(snapshot):
    if snapshot is None:
        return None
    return {"date": snapshot["date"], "score": snapshot["average_score"],
            "popularity": snapshot["popularity"], "in_progress": snapshot["in_progress"]}


def snapshot_result(schedule, snapshots_w1, k=K):
    """Markers, the ep1 and ep3 snapshots, flags and the floor impact of one show. Window-1 data only."""
    markers = final_markers(schedule, trend_markers(snapshots_w1))
    day = {n: markers[n]["day"] for n in markers}
    ep3, ep3_reason = select_snapshot(snapshots_w1, day[3], day[4], k)
    ep1, ep1_reason = select_snapshot(snapshots_w1, day[1], day[2], k)
    return {
        "markers": markers,
        "ep1": snapshot_values(ep1), "ep1_reason": ep1_reason,
        "ep3": snapshot_values(ep3), "ep3_reason": ep3_reason,
        "floor": {"ep1": floor_impact(snapshots_w1, day[1], day[2], k),
                  "ep3": floor_impact(snapshots_w1, day[3], day[4], k)},
        "flags": {"marker_disagreement": bool(trends.marker_disagreement(snapshots_w1, schedule)),
                  "m1_unknown": day[1] is None,
                  "multi_episode_premiere": day[1] is not None and day[2] is not None and not day[1] < day[2]},
    }


def score_features(result):
    """ep1/ep3 features from a snapshot_result. Each is null when the snapshot it needs is missing."""
    ep1, ep3 = result["ep1"], result["ep3"]
    both = ep1 is not None and ep3 is not None
    return {
        "ep1_score": ep1["score"] if ep1 else None,
        "ep3_score": ep3["score"] if ep3 else None,
        "score_delta_1_3": ep3["score"] - ep1["score"] if both else None,
        "ep3_popularity": ep3["popularity"] if ep3 else None,
        "popularity_growth_1_3": round(ep3["popularity"] / ep1["popularity"], 6) if both and ep1["popularity"] else None,
        "ep3_in_progress": ep3["in_progress"] if ep3 else None,
    }


def season_key(season_year, season):
    return (season_year, SEASON_ORDER.index(season))


def previous_season(season_year, season):
    """(year, season) of the season before this one (Winter -> Fall of the year before)."""
    index = SEASON_ORDER.index(season)
    return (season_year, SEASON_ORDER[index - 1]) if index else (season_year - 1, SEASON_ORDER[-1])


def popularity_season_pct(value, peer_values):
    """Percentile (0-100, mid-rank for ties) of `value` among the peers of the SAME season.

    Mild look-sideways: it uses other shows of the same season at their episode-3 time.
    `peer_values` includes the show itself.
    """
    if value is None or not peer_values:
        return None
    below = sum(1 for p in peer_values if p < value)
    equal = sum(1 for p in peer_values if p == value)
    return round(100 * (below + 0.5 * equal) / len(peer_values), 4)


def popularity_vs_previous(value, previous_peer_values):
    """value / median ep3 popularity of the PREVIOUS season (strictly past); None if there is none."""
    if value is None or not previous_peer_values:
        return None
    return round(value / statistics.median(previous_peer_values), 6)


def prequel_features(relations, finale_by_id, ep3_date):
    """is_sequel, prequel_finale_score, prequel_score_known, and the prequels the date rule dropped.

    is_sequel: a PREQUEL relation to an anime of format TV / ONA / TV_SHORT / MOVIE.
    prequel_finale_score: the prequel's primary label, only if the prequel is in our data AND its finale day
    is before this show's ep3 snapshot date (otherwise it was not final yet). With several usable prequels
    the one with the latest finale wins.
    finale_by_id: {anilist id: (primary label score, finale day)} for every show we hold a label for.
    """
    prequels = [r["id"] for r in relations or []
                if r.get("type") == "PREQUEL" and r.get("media_type") == "ANIME" and r.get("format") in PREQUEL_FORMATS]
    known = [(pid, *finale_by_id[pid]) for pid in prequels if pid in finale_by_id]
    usable = [k for k in known if ep3_date is not None and k[2] < ep3_date]
    dropped = sorted(k[0] for k in known if k not in usable)
    best = max(usable, key=lambda k: (k[2], k[0])) if usable else None
    return {"is_sequel": bool(prequels), "prequel_finale_score": best[1] if best else None,
            "prequel_score_known": best is not None, "prequel_dropped_by_date": dropped}


# --- LABELS: window-2 data. Never import these into feature code. ------------------------------------------

def label_offset_unusual(offset_days):
    """Usual = the last releasing record is the finale day itself (offset 0). Anything else is flagged."""
    return offset_days != 0


def primary_label(snapshots_w2, finale_day):
    """The primary label with its offset from the finale day, or None.

    label_offset_days = (date of the last scored releasing record) - (finale day), in whole days.
    """
    found = trends.find_primary_label(snapshots_w2)
    if found is None:
        return None
    score, date, episode = found
    offset = round((date - finale_day).total_seconds() / 86_400)
    return {"score": score, "date": date, "episode": episode, "offset_days": offset,
            "offset_unusual": label_offset_unusual(offset)}


# --- The ledger and the per-show build ---------------------------------------------------------------------

def assign_split(season_year):
    """train <= 2023, validation 2024, test 2025 through Summer 2026. (The aggregation pipeline mirrors this.)"""
    if season_year <= TRAIN_LAST_YEAR:
        return "train"
    return "validation" if season_year == VALIDATION_YEAR else "test"


def assert_splits_disjoint(split_by_id, season_by_id):
    """Every show is in exactly one split and the splits do not overlap in time (train < validation < test)."""
    spans = {}
    for show_id, split in split_by_id.items():
        low, high = spans.get(split, (None, None))
        key = season_key(*season_by_id[show_id])
        spans[split] = (key if low is None else min(low, key), key if high is None else max(high, key))
    ordered = [spans[s] for s in ("train", "validation", "test") if s in spans]
    for (_, earlier_high), (later_low, _) in zip(ordered, ordered[1:]):
        assert earlier_high < later_low, "splits overlap in time"


def ledger(w1_status, result, binge, label):
    """(reasons, subreasons) for one show; no reasons = trainable.

    Reasons, in funnel order: no_w1_records, no_ep1_4_trends, m3_not_before_m4 (+ binge / same_day / inverted),
    no_ep3_snapshot (+ empty_window / lost_to_floor / no_scored_record), ep3_popularity_low, no_primary_label.
    The first reason is the funnel step; the others are listed because they are also true.
    """
    reasons, sub = [], {}
    day = {n: result["markers"][n]["day"] for n in (3, 4)}
    if w1_status != "collected":
        reasons.append("no_w1_records")
    elif day[3] is None or day[4] is None:
        reasons.append("no_ep1_4_trends")
        sub["no_ep1_4_trends"] = "no_m3_m4" if day[3] is None and day[4] is None else ("no_m3" if day[3] is None else "no_m4")
    elif not day[3] < day[4]:
        reasons.append("m3_not_before_m4")
        sub["m3_not_before_m4"] = "binge" if binge else ("same_day" if day[3] == day[4] else "inverted")
    elif result["ep3"] is None:
        reasons.append("no_ep3_snapshot")
        sub["no_ep3_snapshot"] = ("lost_to_floor" if result["floor"]["ep3"]["lost"] else result["ep3_reason"])
    elif result["ep3"]["popularity"] is None or result["ep3"]["popularity"] < POPULARITY_MIN:
        reasons.append("ep3_popularity_low")
    if label is None:
        reasons.append("no_primary_label")
    return reasons, sub


def build_all(candidates, w1_by_id, w2_by_id):
    """One model_a_snapshots document per eligible show: markers, snapshots, features, label, ledger.

    candidates: the model_a_candidates documents (eligible ones are used; w2 shows of any eligibility are not needed).
    w1_by_id / w2_by_id: {_id: list of snapshots}. Features are built from w1 only; w2 goes to primary_label
    and to the prequel lookup (a prequel's label), nowhere else.
    """
    eligible = [c for c in candidates if c.get("eligible")]
    finale_day = {c["_id"]: c["trend_windows"]["w2"]["from"] + DAY for c in eligible if c.get("trend_windows")}
    labels = {c["_id"]: primary_label(w2_by_id.get(c["_id"], []), finale_day[c["_id"]])
              for c in eligible if c["_id"] in finale_day}
    prequel_labels = {i: (lab["score"], finale_day[i]) for i, lab in labels.items() if lab}

    results = {c["_id"]: snapshot_result(c["markers"]["schedule"], w1_by_id.get(c["_id"], [])) for c in eligible}
    peers = {}
    for c in eligible:
        ep3 = results[c["_id"]]["ep3"]
        if ep3 and ep3["popularity"] is not None and ep3["popularity"] >= POPULARITY_MIN:
            peers.setdefault(season_key(c["season_year"], c["season"]), []).append(ep3["popularity"])

    documents = []
    for c in sorted(eligible, key=lambda c: c["_id"]):
        show_id, result, label = c["_id"], results[c["_id"]], labels.get(c["_id"])
        ep3 = result["ep3"]
        popularity = ep3["popularity"] if ep3 else None
        previous = previous_season(c["season_year"], c["season"])
        prequel = prequel_features(c.get("relations"), prequel_labels, ep3["date"] if ep3 else None)
        reasons, subreasons = ledger(c.get("w1_status"), result, trends.is_binge(c), label)
        features = {
            **score_features(result),
            "ep3_popularity_season_pct": popularity_season_pct(popularity, peers.get(season_key(c["season_year"], c["season"]), [])),
            "ep3_popularity_vs_prev_season": popularity_vs_previous(popularity, peers.get(season_key(*previous), [])),
            "is_sequel": prequel["is_sequel"], "prequel_finale_score": prequel["prequel_finale_score"],
            "prequel_score_known": prequel["prequel_score_known"],
        }
        documents.append({
            "_id": show_id, "season": c["season"], "season_year": c["season_year"],
            "status": "excluded" if reasons else "trainable", "reasons": reasons, "subreasons": subreasons,
            "markers": {f"m{n}": result["markers"][n] for n in (1, 2, 3, 4)},
            "ep1": result["ep1"], "ep3": ep3, "ep1_reason": result["ep1_reason"], "ep3_reason": result["ep3_reason"],
            "floor": result["floor"], "features": features, "finale_day": finale_day.get(show_id),
            "label": label, "prequel_dropped_by_date": prequel["prequel_dropped_by_date"],
            "flags": {**result["flags"], "binge": trends.is_binge(c),
                      "label_offset_unusual": bool(label and label["offset_unusual"]),
                      "fallback_w1": c.get("marker_source", {}).get("w1") != "schedule",
                      "fallback_w2": c.get("marker_source", {}).get("w2") != "schedule"},
        })
    return documents
