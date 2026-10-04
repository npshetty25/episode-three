"""Probe: does AniList's daily trend data support Model A? (TASK 003)

Run from the episode-three folder:
    python -m scripts.probe_anilist_trends

What it does:
1. Picks 72 anime from 12 seasons: in each season the 3 most popular shows and
   3 less popular ones (popularity ranks 31-33).
2. Downloads every "releasing" daily trend record and the airing schedule of each.
3. Runs three small experiments with AniList's query filters.
4. Measures the data and writes tables to data/probe/summary.md.

Everything downloaded is saved under data/probe/ (git-ignored). If the script
stops halfway, run it again: saved answers are reused, not downloaded again.
"""
import json
import logging
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from episode_three.clients import anilist
from episode_three.config import PROJECT_ROOT

SEASONS = [("FALL", year) for year in range(2016, 2026)] + [("SPRING", 2026), ("SUMMER", 2026)]
MIN_EPISODES, MAX_EPISODES = 8, 30
PER_GROUP = 3           # shows per group per season
MID_RANK_START = 31     # the "less popular" group is popularity ranks 31-33
PAGE_LIMIT = 20         # safety stop for any multi-page download

PROBE_DIR = PROJECT_ROOT / "data" / "probe"
SEASONS_DIR = PROBE_DIR / "seasons"
SHOWS_DIR = PROBE_DIR / "anilist_trends"
EXPERIMENTS_DIR = PROBE_DIR / "experiments"

# AniList stamps each trend record at midnight Japan time (UTC+9), so we count
# days in Japan time too. Otherwise a record and its airing could look a day apart.
JST = timezone(timedelta(hours=9))

# --- GraphQL queries -------------------------------------------------------
# Each query names exactly the fields we want back. Only filters a query really
# uses are included: AniList rejects mediaTrends filters that are set to null.

SEASON_QUERY = """
query ($season: MediaSeason, $seasonYear: Int, $page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    media(season: $season, seasonYear: $seasonYear, type: ANIME, format_in: [TV, ONA],
          countryOfOrigin: "JP", isAdult: false, sort: POPULARITY_DESC) {
      id idMal title { romaji english } format episodes status popularity averageScore
      startDate { year month day } endDate { year month day }
    }
  }
}"""

TRENDS_QUERY = """
query ($mediaId: Int, $page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    mediaTrends(mediaId: $mediaId, releasing: true, sort: DATE) {
      mediaId date trending averageScore popularity inProgress releasing episode
    }
  }
}"""

AIRING_QUERY = """
query ($mediaId: Int, $page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    airingSchedules(mediaId: $mediaId, sort: TIME) { episode airingAt }
  }
}"""

NOT_RELEASING_QUERY = """
query ($mediaId: Int, $sort: [MediaTrendSort]) {
  Page(page: 1, perPage: 50) {
    pageInfo { hasNextPage }
    mediaTrends(mediaId: $mediaId, releasing: false, sort: $sort) {
      mediaId date averageScore popularity inProgress releasing episode
    }
  }
}"""

AFTER_FINALE_QUERY = """
query ($mediaId: Int, $after: Int) {
  Page(page: 1, perPage: 50) {
    pageInfo { hasNextPage }
    mediaTrends(mediaId: $mediaId, releasing: false, date_greater: $after, sort: DATE) {
      mediaId date averageScore popularity inProgress releasing episode
    }
  }
}"""

EPISODE_LESSER_QUERY = """
query ($mediaId: Int, $page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    mediaTrends(mediaId: $mediaId, releasing: true, episode_lesser: 4, sort: DATE) {
      mediaId date averageScore episode
    }
  }
}"""

MEDIA_ID_IN_QUERY = """
query ($ids: [Int], $page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    mediaTrends(mediaId_in: $ids, releasing: true, sort: DATE) {
      mediaId date averageScore episode
    }
  }
}"""


# --- Saving and downloading ------------------------------------------------

def save_json(path, data):
    """Write data to path via a temporary file, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def cached(path, download):
    """Reuse the saved copy at `path` if there is one; otherwise download and save it."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = download()
    save_json(path, data)
    return data


def all_pages(query, variables):
    """Download page 1, 2, 3... of a Page query until AniList says there are no more.

    We rely on hasNextPage only: AniList's pageInfo.total is a placeholder (5000).
    """
    pages = []
    for page in range(1, PAGE_LIMIT + 1):
        data = anilist.post_query(query, {**variables, "page": page})
        pages.append(data)
        if not data["Page"]["pageInfo"]["hasNextPage"]:
            return pages
    logging.warning("Stopped after %s pages for %s", PAGE_LIMIT, variables)
    return pages


def records_in(pages):
    """All trend records from a list of page answers."""
    return [record for page in pages for record in page["Page"]["mediaTrends"]]


# --- Choosing the sample ---------------------------------------------------

def eligible_shows(pages):
    """Shows with 8-30 planned episodes, still in popularity order."""
    shows = [media for page in pages for media in page["Page"]["media"]]
    return [m for m in shows if m["episodes"] and MIN_EPISODES <= m["episodes"] <= MAX_EPISODES]


def season_listing(season, year):
    """One season's TV/ONA anime by popularity. Fetches extra pages until 33 are eligible."""
    def download():
        pages = []
        for page in range(1, 5):
            data = anilist.post_query(SEASON_QUERY, {"season": season, "seasonYear": year, "page": page})
            pages.append(data)
            enough = len(eligible_shows(pages)) >= MID_RANK_START + PER_GROUP - 1
            if enough or not data["Page"]["pageInfo"]["hasNextPage"]:
                break
        return pages

    return cached(SEASONS_DIR / f"{year}_{season}.json", download)


def build_sample():
    """Pick 3 top and 3 less-popular shows from each season."""
    sample, notes, season_info = [], [], []
    for season, year in SEASONS:
        pages = season_listing(season, year)
        eligible = eligible_shows(pages)
        top = eligible[:PER_GROUP]
        if len(eligible) >= MID_RANK_START + PER_GROUP - 1:
            first_mid_rank = MID_RANK_START
            mid = eligible[MID_RANK_START - 1:MID_RANK_START - 1 + PER_GROUP]
        else:
            mid = [m for m in eligible[-PER_GROUP:] if m not in top]
            first_mid_rank = len(eligible) - len(mid) + 1
            notes.append(f"{season} {year}: only {len(eligible)} eligible shows, so the "
                         f"less-popular group is ranks {first_mid_rank}-{len(eligible)}.")
        season_info.append({"season": season, "year": year, "eligible": len(eligible), "listing_pages": len(pages)})
        for rank, media in enumerate(top, 1):
            sample.append({"season": season, "year": year, "group": "top", "rank": rank, "media": media})
        for offset, media in enumerate(mid):
            sample.append({"season": season, "year": year, "group": "mid", "rank": first_mid_rank + offset, "media": media})
    return sample, notes, season_info


def show_data(media):
    """All releasing trend records and the airing schedule for one show (saved per show)."""
    def download():
        return {
            "media": media,
            "trend_pages": all_pages(TRENDS_QUERY, {"mediaId": media["id"]}),
            "airing_pages": all_pages(AIRING_QUERY, {"mediaId": media["id"]}),
        }

    return cached(SHOWS_DIR / f"{media['id']}.json", download)


# --- Measuring one show ----------------------------------------------------

def jst_day(timestamp):
    """The calendar day in Japan for a Unix timestamp (seconds)."""
    return datetime.fromtimestamp(timestamp, tz=JST).date()


def has_score(record):
    """True if a record has a real score. AniList uses both null and 0 for 'no score yet'."""
    return record is not None and bool(record["averageScore"])


def analyze_show(item, raw, now):
    """Measure one show's trend data. Returns a flat dict of numbers and flags."""
    media = item["media"]
    records = sorted(records_in(raw["trend_pages"]), key=lambda r: r["date"])
    schedule = {s["episode"]: s["airingAt"]
                for page in raw["airing_pages"] for s in page["Page"]["airingSchedules"]}
    aired = {episode: at for episode, at in schedule.items() if at <= now}
    finished = media["status"] == "FINISHED"

    result = {
        "id": media["id"], "title": media["title"]["romaji"], "season": item["season"],
        "year": item["year"], "group": item["group"], "rank": item["rank"],
        "status": media["status"], "episodes": media["episodes"],
        "current_score": media["averageScore"], "finished": finished,
        "trend_pages": len(raw["trend_pages"]),
        "requests": len(raw["trend_pages"]) + len(raw["airing_pages"]),
        "n_records": len(records), "aired_in_schedule": len(aired),
        "schedule_first_episode": min(aired) if aired else None,
        "schedule_has_episodes_1_to_4": all(ep in aired for ep in (1, 2, 3, 4)),
        # Defaults, overwritten below when the data allows:
        "pre_ep4_score": False, "after_ep3_score": False,
        "pre_ep4_popularity": False, "pre_ep4_in_progress": False,
        "after_ep3_popularity": False, "after_ep3_in_progress": False,
        "finale_usable": False if finished else None,
        "usable": False if finished else None,
    }
    # The final episode comes from the schedule, so it is known even without trend records.
    final_episode = max(aired) if aired else None
    final_airing = aired.get(final_episode) if final_episode else None
    result["final_episode"] = final_episode
    result["final_airing_ts"] = final_airing
    result["ep1_airing_ts"] = aired.get(1)
    if not records:
        return result

    # Q2: how regular are the records?
    days = [jst_day(r["date"]) for r in records]
    steps = [(b - a).days for a, b in zip(days, days[1:])]
    result["first_record_day"] = days[0].isoformat()
    result["last_record_day"] = days[-1].isoformat()
    result["pct_daily_steps"] = round(100 * sum(s == 1 for s in steps) / len(steps)) if steps else None
    result["max_gap_days"] = max(steps) if steps else None
    result["same_day_duplicates"] = sum(s == 0 for s in steps)
    # Days with no record inside this show's record range (used to spot AniList outages).
    present = set(days)
    result["missing_days"] = [(days[0] + timedelta(days=i)).isoformat()
                              for i in range((days[-1] - days[0]).days + 1)
                              if days[0] + timedelta(days=i) not in present]
    result["first_daily_step_day"] = next(
        (days[i].isoformat() for i, step in enumerate(steps) if step == 1), None)

    # Q4/Q6: how often each value is present at all.
    n = len(records)
    result["pct_records_with_score"] = round(100 * sum(has_score(r) for r in records) / n)
    result["records_with_score_zero"] = sum(r["averageScore"] == 0 for r in records)
    result["pct_records_with_popularity"] = round(100 * sum(r["popularity"] is not None for r in records) / n)
    result["pct_records_with_in_progress"] = round(100 * sum(r["inProgress"] is not None for r in records) / n)

    # Q3: the episode field compared with the airing schedule.
    first_record_for_episode = {}
    for r in records:
        if r["episode"] is not None:
            first_record_for_episode.setdefault(r["episode"], r)
    episode_records = [r for r in records if r["episode"] is not None]
    offsets = [(jst_day(r["date"]) - jst_day(aired[r["episode"]])).days
               for r in episode_records if r["episode"] in aired]
    result["n_episode_records"] = len(episode_records)
    result["episode_values_below_4"] = sum(1 for r in episode_records if r["episode"] < 4)
    result["episode_compared"] = len(offsets)
    result["episode_within_1_day"] = sum(abs(o) <= 1 for o in offsets)
    result["episode_day_offsets"] = dict(Counter(offsets))
    result["repeated_episode_values"] = sum(
        count - 1 for count in Counter(r["episode"] for r in episode_records).values() if count > 1)
    airing_days = [jst_day(at) for at in aired.values()]
    result["episode_values_off_airing_days"] = sum(
        1 for r in episode_records
        if airing_days and min(abs((jst_day(r["date"]) - d).days) for d in airing_days) > 1)
    records_by_day = {jst_day(r["date"]): r for r in records}
    result["missing_episodes"] = sorted(
        ep for ep, at in aired.items()
        if ep not in first_record_for_episode and days[0] <= jst_day(at) <= days[-1])
    null_on_airing_day = 0
    for at in aired.values():
        record = records_by_day.get(jst_day(at))
        if record is not None and record["episode"] is None:
            null_on_airing_day += 1
    result["airing_days_with_null_episode"] = null_on_airing_day

    # When did episodes 1, 3 and 4 air? Schedule first; trend records as a fallback
    # (some schedules start late, e.g. when episodes 1-4 premiered together).
    def air_time(episode):
        if episode in aired:
            return aired[episode]
        if episode in first_record_for_episode:
            return first_record_for_episode[episode]["date"]
        return None

    ep1, ep3, ep4 = air_time(1), air_time(3), air_time(4)
    result["ep1_airing_ts"] = ep1
    if ep1 and ep4:
        result["ep4_minus_ep1_days"] = (jst_day(ep4) - jst_day(ep1)).days

    # Q4/Q6: the two candidate "after episode 3" snapshots.
    if ep4:
        before = records_by_day.get(jst_day(ep4) - timedelta(days=1))
        result["pre_ep4_score"] = has_score(before)
        result["pre_ep4_popularity"] = before is not None and before["popularity"] is not None
        result["pre_ep4_in_progress"] = before is not None and before["inProgress"] is not None
        if has_score(before):
            result["pre_ep4_score_value"] = before["averageScore"]
    if ep3:
        after = records_by_day.get(jst_day(ep3) + timedelta(days=7))
        result["after_ep3_score"] = has_score(after)
        result["after_ep3_popularity"] = after is not None and after["popularity"] is not None
        result["after_ep3_in_progress"] = after is not None and after["inProgress"] is not None

    first_scored = next((r for r in records if has_score(r)), None)
    if first_scored and ep1:
        result["first_score_days_after_ep1"] = (jst_day(first_scored["date"]) - jst_day(ep1)).days

    # Q5: the finale. Compare the last releasing record with the final episode's airing.
    if finished and final_airing:
        last = records[-1]
        gap = (jst_day(last["date"]) - jst_day(final_airing)).days
        result["finale_gap_days"] = gap
        result["finale_score"] = last["averageScore"] or None
        if has_score(last) and media["averageScore"]:
            result["finale_vs_current"] = abs(last["averageScore"] - media["averageScore"])
        if has_score(last) and "pre_ep4_score_value" in result:
            result["finale_vs_pre_ep4"] = abs(last["averageScore"] - result["pre_ep4_score_value"])
        result["finale_usable"] = -1 <= gap <= 7 and has_score(last)
    if finished:
        result["usable"] = result["pre_ep4_score"] and result["finale_usable"]

    # Oddities worth reporting.
    scores = [r["averageScore"] for r in records if has_score(r)]
    result["max_daily_score_jump"] = max((abs(b - a) for a, b in zip(scores, scores[1:])), default=None)
    popularity = [r["popularity"] for r in records if r["popularity"] is not None]
    result["popularity_drops"] = sum(b < a for a, b in zip(popularity, popularity[1:]))
    return result


# --- Experiments -----------------------------------------------------------

def run_experiments(analyses):
    """Three small tests of AniList's filters (Q8)."""
    results = {}
    by_key = {(a["season"], a["year"], a["group"], a["rank"]): a for a in analyses}

    # 1. releasing: false. Do records exist before airing and after the finale?
    results["not_releasing"] = []
    for year in (2016, 2021, 2025):
        show = by_key.get(("FALL", year, "top", 1))
        if show is None or not show.get("final_airing_ts"):
            continue
        media_id, finale = show["id"], show["final_airing_ts"]

        def download():
            return {
                "earliest": anilist.post_query(NOT_RELEASING_QUERY, {"mediaId": media_id, "sort": ["DATE"]}),
                "latest": anilist.post_query(NOT_RELEASING_QUERY, {"mediaId": media_id, "sort": ["DATE_DESC"]}),
                "after_finale": anilist.post_query(AFTER_FINALE_QUERY, {"mediaId": media_id, "after": finale}),
            }

        raw = cached(EXPERIMENTS_DIR / f"not_releasing_{media_id}.json", download)
        results["not_releasing"].append(summarize_not_releasing(show, raw))

    # 2. episode_lesser: 4. Does it skip days where episode is null?
    #    Needs a show whose own records include episodes below 4 (multi-episode
    #    premieres like Kusuriya have none, which makes the test meaningless).
    show = next((a for a in analyses if a["season"] == "FALL" and a["year"] == 2023
                 and a.get("episode_values_below_4")), None)
    if show:
        media_id = show["id"]
        pages = cached(EXPERIMENTS_DIR / f"episode_lesser_4_{media_id}.json",
                       lambda: all_pages(EPISODE_LESSER_QUERY, {"mediaId": media_id}))
        returned = records_in(pages)
        local = records_in(json.loads((SHOWS_DIR / f"{media_id}.json").read_text(encoding="utf-8"))["trend_pages"])
        results["episode_lesser"] = {
            "id": media_id, "title": show["title"], "requests": len(pages),
            "returned_records": len(returned),
            "returned_episode_values": dict(Counter(str(r["episode"]) for r in returned)),
            "local_records_total": len(local),
            "local_records_episode_below_4": sum(1 for r in local if r["episode"] is not None and r["episode"] < 4),
            "local_records_episode_null": sum(r["episode"] is None for r in local),
        }

    # 3. mediaId_in: can one query return several shows' records?
    mids = [a for a in analyses if a["season"] == "FALL" and a["year"] == 2023
            and a["group"] == "mid" and a["n_records"]]
    if len(mids) >= 2:
        ids = [a["id"] for a in mids]
        saved = cached(EXPERIMENTS_DIR / "media_id_in.json",
                       lambda: {"ids": ids, "pages": all_pages(MEDIA_ID_IN_QUERY, {"ids": ids})})
        returned = records_in(saved["pages"])
        per_show = Counter(r["mediaId"] for r in returned)
        results["media_id_in"] = {
            "ids": ids,
            "returned_per_show": {str(i): per_show.get(i, 0) for i in ids},
            "individual_per_show": {str(a["id"]): a["n_records"] for a in mids},
            "first_page_show_ids": sorted({r["mediaId"] for r in saved["pages"][0]["Page"]["mediaTrends"]}),
            "requests_combined": len(saved["pages"]),
            "requests_individual": sum(a["trend_pages"] for a in mids),
        }
    return results


def summarize_not_releasing(show, raw):
    """What the releasing: false records look like for one show."""
    earliest = raw["earliest"]["Page"]["mediaTrends"]
    latest = raw["latest"]["Page"]["mediaTrends"]
    after = raw["after_finale"]["Page"]["mediaTrends"]
    ep1 = show.get("ep1_airing_ts")
    summary = {
        "id": show["id"], "title": show["title"], "season": f"{show['season']} {show['year']}",
        "final_airing_day": jst_day(show["final_airing_ts"]).isoformat(),
        "requests": 3,
    }
    if earliest:
        summary["earliest_day"] = jst_day(earliest[0]["date"]).isoformat()
        summary["first_page_records_before_ep1"] = sum(1 for r in earliest if ep1 and r["date"] < ep1)
    if latest:
        summary["latest_day"] = jst_day(latest[0]["date"]).isoformat()
    summary["after_finale_on_first_page"] = len(after)
    summary["after_finale_more_pages"] = raw["after_finale"]["Page"]["pageInfo"]["hasNextPage"]
    if after:
        days = [jst_day(r["date"]) for r in after]
        steps = [(b - a).days for a, b in zip(days, days[1:])]
        summary["after_finale_first_day"] = days[0].isoformat()
        summary["after_finale_pct_daily_steps"] = round(100 * sum(s == 1 for s in steps) / len(steps)) if steps else None
        summary["after_finale_pct_with_score"] = round(100 * sum(has_score(r) for r in after) / len(after))
        if latest:
            summary["after_finale_span_days"] = (jst_day(latest[0]["date"]) - days[0]).days + 1
        # How much does the score still move after the finale?
        final_day = jst_day(show["final_airing_ts"])
        after_by_day = {jst_day(r["date"]): r for r in after}
        for offset in (7, 14, 30):
            record = after_by_day.get(final_day + timedelta(days=offset))
            summary[f"score_finale_plus_{offset}d"] = record["averageScore"] if record else None
    summary["score_last_releasing_record"] = show.get("finale_score")
    summary["score_current"] = show["current_score"]
    return summary


# --- Summary tables --------------------------------------------------------

def fmt_pct(flags):
    """'83% (10/12)' from a list of True/False, ignoring None (not applicable)."""
    known = [f for f in flags if f is not None]
    if not known:
        return "n/a"
    hits = sum(1 for f in known if f)
    return f"{round(100 * hits / len(known))}% ({hits}/{len(known)})"


def fmt_median(values):
    known = [v for v in values if v is not None]
    return f"{statistics.median(known):g}" if known else "n/a"


def fmt_range(values):
    known = [v for v in values if v is not None]
    return f"{min(known)} to {max(known)}" if known else "n/a"


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def row_groups(shows):
    """Each season in order, then top vs less-popular across all seasons, then everything."""
    groups = [(f"{season.title()} {year}", [s for s in shows if s["season"] == season and s["year"] == year])
              for season, year in SEASONS]
    groups.append(("**Top 3, all seasons**", [s for s in shows if s["group"] == "top"]))
    groups.append(("**Ranks 31-33, all seasons**", [s for s in shows if s["group"] == "mid"]))
    groups.append(("**All**", shows))
    return groups


def build_summary(shows, experiments, notes, season_info, run):
    groups = row_groups(shows)
    with_records = [s for s in shows if s["n_records"]]
    out = ["# TASK 003 probe: generated tables", ""]

    out += ["## Sample", "", table(
        ["Season", "Eligible shows (8-30 eps)", "Listing pages", "Sampled"],
        [[f"{i['season'].title()} {i['year']}", i["eligible"], i["listing_pages"],
          sum(1 for s in shows if s["season"] == i["season"] and s["year"] == i["year"])] for i in season_info])]
    out += [""] + [f"- {note}" for note in notes] + [""]

    out += ["## Q1 + headline: is a show usable for Model A?", "", table(
        ["Group", "Shows", "Any releasing records", "Score on day before ep 4",
         "Score 7 days after ep 3", "Usable finale (finished shows)", "Usable (both)"],
        [[label, len(g), fmt_pct([s["n_records"] > 0 for s in g]), fmt_pct([s["pre_ep4_score"] for s in g]),
          fmt_pct([s["after_ep3_score"] for s in g]), fmt_pct([s["finale_usable"] for s in g]),
          fmt_pct([s["usable"] for s in g])] for label, g in groups]), ""]

    out += ["## Q2: record density", "", table(
        ["Group", "Median records", "Range", "Median % of 1-day steps", "Largest gap (days)", "Same-day duplicates"],
        [[label, fmt_median([s["n_records"] for s in g]), fmt_range([s["n_records"] for s in g]),
          fmt_median([s.get("pct_daily_steps") for s in g]),
          fmt_range([s.get("max_gap_days") for s in g]).split(" to ")[-1],
          sum(s.get("same_day_duplicates", 0) for s in g)] for label, g in groups]), ""]

    q3_rows = []
    for label, g in groups:
        compared = sum(s.get("episode_compared", 0) for s in g)
        within = sum(s.get("episode_within_1_day", 0) for s in g)
        offsets = Counter()
        for s in g:
            offsets.update({int(k): v for k, v in s.get("episode_day_offsets", {}).items()})
        q3_rows.append([
            label, compared, f"{round(100 * within / compared)}%" if compared else "n/a",
            ", ".join(f"{k:+d}: {v}" for k, v in sorted(offsets.items())) or "n/a",
            sum(1 for s in g if s.get("missing_episodes")),
            sum(s.get("episode_values_off_airing_days", 0) for s in g),
            sum(s.get("airing_days_with_null_episode", 0) for s in g),
            sum(1 for s in g if s["aired_in_schedule"] == 0),
            sum(1 for s in g if (s.get("schedule_first_episode") or 1) > 1)])
    # Days missing for 3+ shows at once are AniList outages, not show-specific gaps.
    missing = Counter(d for s in with_records for d in s.get("missing_days", []))
    daily_shows = [s for s in with_records if s.get("first_daily_step_day")]
    outage_days = sorted(d for d, count in missing.items() if count >= 3 and d >= "2018-03-20")
    out += ["### Daily records and outages", "",
            f"- Earliest 1-day step between records: {min(s['first_daily_step_day'] for s in daily_shows)} "
            "(before that, records exist only on episode days).",
            f"- Days missing for 3+ sampled shows at once (since daily records began): "
            f"{', '.join(outage_days) or 'none'}", ""]

    out += ["## Q3: the episode field vs the airing schedule", "", table(
        ["Group", "Episode values compared", "Within ±1 day of airing", "Day offset (record − airing): count",
         "Shows with missing episodes", "Episode values >1 day from any airing",
         "Airing days whose record has no episode", "Shows without schedule", "Schedules starting after ep 1"],
        q3_rows), ""]

    out += ["## Q4: averageScore availability", "", table(
        ["Group", "Median % of records with a score", "Records with score 0", "First score: days after ep 1 (median)",
         "First score: range", "Score on day before ep 4", "Score 7 days after ep 3"],
        [[label, fmt_median([s.get("pct_records_with_score") for s in g]),
          sum(s.get("records_with_score_zero", 0) for s in g),
          fmt_median([s.get("first_score_days_after_ep1") for s in g]),
          fmt_range([s.get("first_score_days_after_ep1") for s in g]),
          fmt_pct([s["pre_ep4_score"] for s in g]), fmt_pct([s["after_ep3_score"] for s in g])]
         for label, g in groups]), ""]

    out += ["## Q5: the finale", "", table(
        ["Group", "Finished shows", "Finale gap in days (median)", "Gap range", "Finale score present",
         "Median abs(finale − current)", "Median abs(finale − score before ep 4)"],
        [[label, sum(1 for s in g if s["finished"]), fmt_median([s.get("finale_gap_days") for s in g]),
          fmt_range([s.get("finale_gap_days") for s in g]),
          fmt_pct([s.get("finale_score") is not None if "finale_gap_days" in s else None for s in g]),
          fmt_median([s.get("finale_vs_current") for s in g]), fmt_median([s.get("finale_vs_pre_ep4") for s in g])]
         for label, g in groups]), ""]

    out += ["## Q6: popularity and inProgress", "", table(
        ["Group", "Popularity, day before ep 4", "inProgress, day before ep 4", "Popularity, 7 days after ep 3",
         "inProgress, 7 days after ep 3", "Median % records with popularity", "Median % records with inProgress"],
        [[label, fmt_pct([s["pre_ep4_popularity"] for s in g]), fmt_pct([s["pre_ep4_in_progress"] for s in g]),
          fmt_pct([s["after_ep3_popularity"] for s in g]), fmt_pct([s["after_ep3_in_progress"] for s in g]),
          fmt_median([s.get("pct_records_with_popularity") for s in g]),
          fmt_median([s.get("pct_records_with_in_progress") for s in g])] for label, g in groups]), ""]

    listing_pages = sum(i["listing_pages"] for i in season_info)
    show_requests = sum(s["requests"] for s in shows)
    experiment_requests = (sum(e["requests"] for e in experiments.get("not_releasing", []))
                           + experiments.get("episode_lesser", {}).get("requests", 0)
                           + experiments.get("media_id_in", {}).get("requests_combined", 0))
    out += ["## Q7: request cost", "",
            f"- Requests needed for the whole probe: {listing_pages + show_requests + experiment_requests} "
            f"({listing_pages} season listings + {show_requests} for shows + {experiment_requests} for experiments)",
            f"- Requests per show (trend pages + airing schedule): median {fmt_median([s['requests'] for s in shows])}, "
            f"range {fmt_range([s['requests'] for s in shows])}",
            f"- Trend records per show: mean {statistics.mean(s['n_records'] for s in shows):.1f}",
            f"- This run: {run['requests']} HTTP requests, {run['retries']} retries, {run['http_429']} HTTP 429, "
            f"{run['runtime_seconds']} s. X-RateLimit-Limit seen: {run['limit_values']}, "
            f"lowest X-RateLimit-Remaining: {run['lowest_remaining']}", ""]

    out += ["## Q8: experiments", "", "```json", json.dumps(experiments, indent=1, ensure_ascii=False), "```", ""]

    out += ["## Oddities", ""]
    for s in with_records:
        oddities = []
        if (s.get("max_daily_score_jump") or 0) >= 5:
            oddities.append(f"score jumped {s['max_daily_score_jump']} points in one day")
        if s.get("popularity_drops"):
            oddities.append(f"popularity fell {s['popularity_drops']} times")
        if s.get("repeated_episode_values"):
            oddities.append(f"{s['repeated_episode_values']} repeated episode values")
        if s.get("ep4_minus_ep1_days") is not None and s["ep4_minus_ep1_days"] < 14:
            oddities.append(f"ep 4 aired {s['ep4_minus_ep1_days']} days after ep 1")
        if s.get("final_episode") and s["episodes"] and s["finished"] and s["final_episode"] != s["episodes"]:
            oddities.append(f"schedule ends at ep {s['final_episode']} of {s['episodes']}")
        if oddities:
            out.append(f"- {s['season']} {s['year']} {s['group']} #{s['rank']} {s['title']} ({s['id']}): "
                       + "; ".join(oddities))
    out.append("")

    out += ["## Per show", "", table(
        ["Season", "Group", "AniList ID", "Records", "First record (JST)", "Schedule (aired, first ep)",
         "Score before ep 4", "Finale gap", "Finale score", "Current score", "Usable"],
        [[f"{s['season'].title()} {s['year']}", f"{s['group']} #{s['rank']}", s["id"], s["n_records"],
          s.get("first_record_day", "-"), f"{s['aired_in_schedule']}, {s.get('schedule_first_episode')}",
          s.get("pre_ep4_score_value", "-"),
          s.get("finale_gap_days", "-"), s.get("finale_score", "-"), s["current_score"], s["usable"]]
         for s in shows])]
    return "\n".join(out) + "\n"


# --- Main ------------------------------------------------------------------

def setup_logging():
    """Every request goes to data/probe/probe.log; only warnings (retries, 429) to the screen."""
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    logfile = logging.FileHandler(PROBE_DIR / "probe.log", encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logfile, console])


def main():
    setup_logging()
    started = time.monotonic()
    now = time.time()
    print("Probing AniList trend data. First run: about 300 requests at ~27/minute "
          "(roughly 12-20 minutes). Re-runs reuse saved data.", flush=True)

    sample, notes, season_info = build_sample()
    print(f"Sample: {len(sample)} shows from {len(SEASONS)} seasons", flush=True)

    analyses = []
    for number, item in enumerate(sample, 1):
        analysis = analyze_show(item, show_data(item["media"]), now)
        analyses.append(analysis)
        title = analysis["title"].encode("ascii", "replace").decode("ascii")
        print(f"[{number:>2}/{len(sample)}] {item['season']} {item['year']} {item['group']} #{item['rank']}: "
              f"{title[:40]}: {analysis['n_records']} records", flush=True)

    print("Running experiments...", flush=True)
    experiments = run_experiments(analyses)
    run = {"runtime_seconds": round(time.monotonic() - started), **anilist.stats}
    save_json(PROBE_DIR / "analysis.json",
              {"shows": analyses, "experiments": experiments, "run": run, "notes": notes, "seasons": season_info})
    summary_path = PROBE_DIR / "summary.md"
    summary_path.write_text(build_summary(analyses, experiments, notes, season_info, run), encoding="utf-8")

    finished = [a for a in analyses if a["finished"]]
    print("\nSummary")
    print(f"  Shows with any releasing records: {fmt_pct([a['n_records'] > 0 for a in analyses])}")
    print(f"  Score on the day before ep 4:     {fmt_pct([a['pre_ep4_score'] for a in analyses])}")
    print(f"  Usable finale (finished shows):   {fmt_pct([a['finale_usable'] for a in finished])}")
    print(f"  Usable for Model A (both):        {fmt_pct([a['usable'] for a in finished])}")
    print(f"  This run: {run['requests']} requests, {run['http_429']} x HTTP 429, "
          f"{run['retries']} retries, {run['runtime_seconds']} s")
    print(f"  Tables: {summary_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except anilist.AniListError as error:
        print(f"\nProbe stopped: {error}\nRun it again to continue; saved data is reused.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped by you. Run it again to continue; saved data is reused.", file=sys.stderr)
        sys.exit(1)
