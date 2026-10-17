"""Pure helpers for the airing-schedule probe (TASK 007).

Question being answered: are AniList's PAST airing schedules complete enough to compute
the marker days M(n) of spec section 7? AniList only guarantees future airing data, so the
coverage for finished shows has to be measured, not assumed.
"""
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))  # AniList trend days are Japan days

# The schedule query for a batch of shows. Only the filters it uses are passed (null filters fail).
AIRING_QUERY = """
query ($ids: [Int], $page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    airingSchedules(mediaId_in: $ids, sort: [TIME]) { mediaId episode airingAt }
  }
}"""


def pick_probe_shows(candidate_docs, how_many=10):
    """Choose `how_many` eligible candidates, evenly spaced from most to least popular.

    Evenly spaced (not the top 10) so the probe sees both well-known and obscure shows.
    The choice depends only on the data, so re-running picks the same shows.
    """
    eligible = sorted((doc for doc in candidate_docs if doc.get("eligible")),
                      key=lambda doc: (-(doc.get("current_popularity") or 0), doc["_id"]))
    if len(eligible) <= how_many:
        return eligible
    step = (len(eligible) - 1) / (how_many - 1)
    return [eligible[round(i * step)] for i in range(how_many)]


def anilist_id(doc):
    """AniList's numeric id from a candidate _id like 'anilist:154587'."""
    return int(doc["_id"].split(":")[1])


def to_jst(unix_seconds):
    return datetime.fromtimestamp(unix_seconds, tz=JST).strftime("%Y-%m-%d %H:%M")


def summarize_show_schedule(rows, episodes):
    """Measure one show's schedule rows against its episode count.

    `rows` are airingSchedules rows ({episode, airingAt, ...}) for ONE show.
    """
    seen = {row["episode"] for row in rows}
    times = [row["airingAt"] for row in rows]
    expected = set(range(1, episodes + 1)) if episodes else set()
    if not rows:
        status = "missing"
    elif expected and expected <= seen:
        status = "complete"
    else:
        status = "gaps"
    return {
        "rows": len(rows),
        "episodes_expected": episodes,
        "distinct_episodes": len(seen),
        "has_eps_1_to_4": {1, 2, 3, 4} <= seen,
        "has_final_episode": bool(episodes) and episodes in seen,
        "missing_episodes": sorted(expected - seen),
        "first_airing_jst": to_jst(min(times)) if times else None,
        "last_airing_jst": to_jst(max(times)) if times else None,
        "status": status,
    }


def season_verdict(summaries):
    """One-line verdict for a season's probed shows: complete, gaps or missing."""
    total = len(summaries)
    if total == 0:
        return "no shows probed", "none"
    counts = {name: sum(1 for s in summaries if s["status"] == name) for name in ("complete", "gaps", "missing")}
    both = sum(1 for s in summaries if s["has_eps_1_to_4"] and s["has_final_episode"])
    if counts["complete"] == total:
        verdict = "complete"
    elif counts["missing"] == total:
        verdict = "missing"
    else:
        verdict = "gaps"
    detail = (f"{counts['complete']} complete, {counts['gaps']} with gaps, {counts['missing']} missing; "
              f"{both}/{total} have eps 1-4 AND the final episode")
    return detail, verdict


def group_rows_by_show(rows):
    """{mediaId: [rows]} from a flat list of airingSchedules rows."""
    grouped = {}
    for row in rows:
        grouped.setdefault(row["mediaId"], []).append(row)
    return grouped
