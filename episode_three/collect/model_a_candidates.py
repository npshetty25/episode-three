"""Build the list of anime that Model A can use (Fall 2018 -> Summer 2026).

Every show AniList lists for a season is stored in the model_a_candidates collection,
together with whether it is eligible and, if not, WHY. Recording the reasons makes the
dataset auditable ("31% were excluded as not 8-30 episodes").

The popularity filter in the listing query uses TODAY's popularity. That is fine for
choosing which shows to download (it only widens the net), but it is never a model
feature, because today's popularity contains the future.
"""
from collections import Counter
from datetime import datetime, timezone

from pymongo import UpdateOne

from episode_three import anilist_sync
from episode_three.clients import anilist

COLLECTION = "model_a_candidates"
JOB = "model_a_candidates"

SEASONS = ["WINTER", "SPRING", "SUMMER", "FALL"]
FIRST_SEASON, FIRST_YEAR = "FALL", 2018
LAST_SEASON, LAST_YEAR = "SUMMER", 2026

MIN_EPISODES, MAX_EPISODES = 8, 30
MIN_DURATION_MIN = 10
LISTING_REQUEST_CAP = 100   # the task's budget for the listing
PER_PAGE_STEPS = (50, 25)   # fall back to 25 per page if AniList reports a complexity error
MAX_PAGES = 10              # safety stop for one season

# One season of candidates. popularity_greater uses current popularity as a pre-filter only.
SEASON_QUERY = """
query ($season: MediaSeason, $seasonYear: Int, $page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { hasNextPage }
    media(season: $season, seasonYear: $seasonYear, type: ANIME,
          format_in: [TV, ONA], countryOfOrigin: "JP", isAdult: false,
          popularity_greater: 1999, sort: [POPULARITY_DESC, ID]) {
      id idMal title { romaji english } format status episodes duration
      season seasonYear startDate { year month day } endDate { year month day }
      source countryOfOrigin isAdult genres
      studios(isMain: true) { nodes { name } }
      averageScore popularity
      relations { edges { relationType node { id type format } } }
    }
  }
}"""


class RequestBudgetExceeded(Exception):
    """The next request would go over the task's request cap."""


# --- Pure functions (tested offline) ---------------------------------------

def season_range():
    """Yield (season, year) from Fall 2018 to Summer 2026 in calendar order (32 seasons)."""
    first = (FIRST_YEAR, SEASONS.index(FIRST_SEASON))
    last = (LAST_YEAR, SEASONS.index(LAST_SEASON))
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        for index, season in enumerate(SEASONS):
            if first <= (year, index) <= last:
                yield season, year


def check_eligibility(media):
    """Decide whether a show can be used by Model A. Returns (eligible, reasons).

    A show can fail several rules at once, so `reasons` is a list of codes:
    format, country, adult, episodes_unknown, episodes_out_of_range (not 8-30),
    duration_unknown, duration_short (under 10 minutes), not_finished.
    (The "popularity at episode 3" rule needs trend data and comes later.)
    """
    reasons = []
    if media.get("format") not in ("TV", "ONA"):
        reasons.append("format")
    if media.get("countryOfOrigin") != "JP":
        reasons.append("country")
    if media.get("isAdult"):
        reasons.append("adult")
    episodes = media.get("episodes")
    if episodes is None:
        reasons.append("episodes_unknown")
    elif not MIN_EPISODES <= episodes <= MAX_EPISODES:
        reasons.append("episodes_out_of_range")
    duration = media.get("duration")
    if duration is None:
        reasons.append("duration_unknown")
    elif duration < MIN_DURATION_MIN:
        reasons.append("duration_short")
    if media.get("status") != "FINISHED":
        reasons.append("not_finished")
    return not reasons, reasons


def to_candidate_doc(media, listed_at=None):
    """One AniList media -> one model_a_candidates document.

    current_average_score and current_popularity are for ANALYSIS ONLY, never features.
    """
    eligible, reasons = check_eligibility(media)
    studios = ((media.get("studios") or {}).get("nodes")) or []
    edges = ((media.get("relations") or {}).get("edges")) or []
    relations = [{"type": edge["relationType"],
                  "id": f"anilist:{edge['node']['id']}",
                  "media_type": edge["node"].get("type"),
                  "format": edge["node"].get("format")}
                 for edge in edges if edge.get("node")]
    return {
        "_id": f"anilist:{media['id']}",
        "source": "anilist",
        "mal_id": media.get("idMal"),
        "title": media.get("title"),
        "format": media.get("format"),
        "status": media.get("status"),
        "episodes": media.get("episodes"),
        "duration_min": media.get("duration"),
        "season": media.get("season"),
        "season_year": media.get("seasonYear"),
        "start_date": anilist_sync.fuzzy_date(media.get("startDate")),
        "end_date": anilist_sync.fuzzy_date(media.get("endDate")),
        "source_material": media.get("source"),
        "country": media.get("countryOfOrigin"),
        "is_adult": media.get("isAdult"),
        "genres": media.get("genres") or [],
        "main_studios": [node["name"] for node in studios],
        "relations": relations,
        "current_average_score": media.get("averageScore"),
        "current_popularity": media.get("popularity"),
        "eligible": eligible,
        "exclusion_reasons": reasons,
        "listed_at": listed_at or datetime.now(timezone.utc),
    }


def dedupe_by_id(media_list):
    """Keep each show once, in first-seen order. Popularity can shift between pages, so a show can repeat."""
    seen = {}
    for media in media_list:
        seen.setdefault(media["id"], media)
    return list(seen.values())


# --- Talking to AniList -----------------------------------------------------

def list_season(season, year, requests_at_start, request_cap=LISTING_REQUEST_CAP, per_page_steps=PER_PAGE_STEPS):
    """Download one season's candidate shows. Returns (shows, per_page_used).

    Pages are fetched until hasNextPage is false. If AniList reports a complexity error,
    the season is restarted with the next, smaller page size.
    """
    for step, per_page in enumerate(per_page_steps):
        try:
            return dedupe_by_id(_all_pages(season, year, per_page, requests_at_start, request_cap)), per_page
        except anilist.AniListError as error:
            is_last_step = step == len(per_page_steps) - 1
            if "complex" in str(error).lower() and not is_last_step:
                continue
            raise
    raise AssertionError("per_page_steps must not be empty")


def _all_pages(season, year, per_page, requests_at_start, request_cap):
    shows = []
    for page in range(1, MAX_PAGES + 1):
        if anilist.stats["requests"] - requests_at_start >= request_cap:
            raise RequestBudgetExceeded(f"stopping before {season} {year} page {page}: "
                                        f"the cap of {request_cap} requests would be exceeded")
        data = anilist.post_query(SEASON_QUERY, {"season": season, "seasonYear": year,
                                                 "page": page, "perPage": per_page})
        shows.extend(data["Page"]["media"])
        if not data["Page"]["pageInfo"]["hasNextPage"]:
            return shows
    raise anilist.AniListError(f"{season} {year}: more than {MAX_PAGES} pages; stopping as a safety measure")


# --- Storing ----------------------------------------------------------------

def collect_season(db, season, year, requests_at_start, request_cap=LISTING_REQUEST_CAP):
    """List one season, store its candidates (one bulk write) and record it as done."""
    requests_before = anilist.stats["requests"]
    shows, per_page = list_season(season, year, requests_at_start, request_cap)
    listed_at = datetime.now(timezone.utc)
    docs = [to_candidate_doc(media, listed_at) for media in shows]
    if docs:
        db[COLLECTION].bulk_write(
            [UpdateOne({"_id": doc["_id"]}, {"$set": {k: v for k, v in doc.items() if k != "_id"}}, upsert=True)
             for doc in docs], ordered=False)

    reasons = Counter(code for doc in docs for code in doc["exclusion_reasons"])
    counts = {"listed": len(docs), "eligible": sum(1 for doc in docs if doc["eligible"]),
              "exclusion_reasons": dict(sorted(reasons.items())), "per_page": per_page}
    requests_used = anilist.stats["requests"] - requests_before
    # The "this season is done" marker is written LAST, so a crash mid-season is simply redone.
    db["sync_runs"].replace_one({"_id": run_id(season, year)}, {
        "_id": run_id(season, year), "job": JOB, "season": season, "season_year": year,
        "finished_at": datetime.now(timezone.utc), "requests_used": requests_used, "counts": counts,
    }, upsert=True)
    return {"season": season, "year": year, "requests": requests_used, **counts}


def run_id(season, year):
    return f"{JOB}:{season}:{year}"


def completed_seasons(db):
    """The (season, year) pairs already collected, from sync_runs."""
    return {(run["season"], run["season_year"])
            for run in db["sync_runs"].find({"job": JOB}, {"season": 1, "season_year": 1})}


def create_indexes(db):
    db[COLLECTION].create_index([("season_year", 1), ("season", 1)])
    db[COLLECTION].create_index("eligible")


def summary_from_db(db):
    """Per-season counts and the exclusion-reason totals for everything stored."""
    per_season = {}
    for row in db[COLLECTION].aggregate([
            {"$group": {"_id": {"season": "$season", "year": "$season_year"},
                        "listed": {"$sum": 1},
                        "eligible": {"$sum": {"$cond": ["$eligible", 1, 0]}}}}]):
        per_season[(row["_id"]["season"], row["_id"]["year"])] = (row["listed"], row["eligible"])
    reasons = {row["_id"]: row["count"] for row in db[COLLECTION].aggregate([
        {"$unwind": "$exclusion_reasons"}, {"$group": {"_id": "$exclusion_reasons", "count": {"$sum": 1}}}])}
    return per_season, reasons
