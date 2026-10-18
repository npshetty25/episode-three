"""Model B show features from AniList, for every anime Model B trains on or scores.

One definition, one source (spec v1.3 ruling 3): the show features of the Kaggle training anime AND of Nirav's anime
come from the same AniList query. Kaggle ids (MAL ids) map through idMal_in; AniList ids through id_in. Pure functions
here; scripts/collect_model_b_anime.py does the I/O. A MAL id AniList does not know is RECORDED as unmapped, never guessed.
"""
from episode_three.clients import anilist

COLLECTION = "model_b_anime"
UNMAPPED = "model_b_unmapped"
JOB = "model_b_anime"
PER_PAGE = 50
TASK_REQUEST_CAP = 160
MEDIA_FIELDS = """id idMal format status episodes duration source countryOfOrigin isAdult genres
        averageScore popularity startDate { year }
        stats { statusDistribution { status amount } }"""


def query(filter_name):
    """The one query, with only the filter it uses (null filters make AniList answer 500/400)."""
    variable = "$malIds" if filter_name == "idMal_in" else "$ids"
    return f"""
query ({variable}: [Int], $page: Int, $perPage: Int) {{
  Page(page: $page, perPage: $perPage) {{
    pageInfo {{ hasNextPage }}
    media({filter_name}: {variable}, type: ANIME) {{
        {MEDIA_FIELDS} }}
  }}
}}"""


QUERY_BY_MAL_ID = query("idMal_in")
QUERY_BY_ANILIST_ID = query("id_in")

# Nirav's entries Model B uses: finished/dropped TV for his features, planned/current for predictions.
FEATURE_STATUSES = ("COMPLETED", "DROPPED", "REPEATING")
PREDICTION_STATUSES = ("PLANNING", "CURRENT")


# --- The universe --------------------------------------------------------------------------------------------------

def nirav_titles(entries, titles_by_id):
    """The AniList titles of Nirav's entries that Model B needs show features for (adult titles skipped).

    TV completed / dropped / repeating entries (his features) plus PLANNING and CURRENT entries of any format
    (shows he may want a prediction for). Returns {title _id: title document}.
    """
    chosen = {}
    for entry in entries:
        title = titles_by_id.get(entry["title_id"])
        if title is None or title.get("is_adult") or entry.get("anilist_status") is None:
            continue
        status = entry["anilist_status"]
        if (status in FEATURE_STATUSES and title.get("format") == "TV") or status in PREDICTION_STATUSES:
            chosen[title["_id"]] = title
    return chosen


def build_universe(sample_anime_ids, entries, titles_by_id):
    """The anime to fetch, deduplicated before any request.

    sample_anime_ids: the MAL ids in the Kaggle sample. Nirav's titles that carry a mal_id are fetched with the
    Kaggle ids through idMal_in (one route, no duplicates); titles without one go through id_in.
    Returns a dict with the two id lists and the counts for the plan (Kaggle / Nirav / overlap / total).
    """
    kaggle = {int(i) for i in sample_anime_ids}
    nirav = nirav_titles(entries, titles_by_id)
    nirav_mal = {t["mal_id"] for t in nirav.values() if t.get("mal_id") is not None}
    nirav_without_mal = {t["anilist_id"] for t in nirav.values() if t.get("mal_id") is None}
    return {
        "mal_ids": sorted(kaggle | nirav_mal), "anilist_ids": sorted(nirav_without_mal),
        "kaggle": len(kaggle), "nirav": len(nirav), "overlap": len(kaggle & nirav_mal),
        "total": len(kaggle | nirav_mal) + len(nirav_without_mal),
    }


def todo_ids(universe, stored_mal_ids, stored_anilist_ids, unmapped_mal_ids, force=False):
    """The ids still to fetch: those already stored (or already known to be unmapped) are skipped unless force."""
    if force:
        return list(universe["mal_ids"]), list(universe["anilist_ids"])
    done_mal = set(stored_mal_ids) | set(unmapped_mal_ids)
    return ([i for i in universe["mal_ids"] if i not in done_mal],
            [i for i in universe["anilist_ids"] if i not in set(stored_anilist_ids)])


def chunk(ids, size=PER_PAGE):
    return [ids[start:start + size] for start in range(0, len(ids), size)]


def planned_requests(n_mal, n_anilist, per_page=PER_PAGE):
    """One request per chunk of ids: a chunk's answer has at most as many rows as ids, so no second page is needed."""
    return -(-n_mal // per_page) + -(-n_anilist // per_page)


# --- Mapping and storing -------------------------------------------------------------------------------------------

def drop_share(distribution):
    """DROPPED / (COMPLETED + DROPPED) from raw statusDistribution amounts; None if nobody completed or dropped."""
    completed, dropped = distribution.get("COMPLETED", 0), distribution.get("DROPPED", 0)
    return dropped / (completed + dropped) if completed + dropped > 0 else None


def to_model_b_anime_doc(media):
    """One AniList media -> one model_b_anime document. Only the raw statusDistribution is kept from stats."""
    distribution = {row["status"]: row["amount"] for row in (media.get("stats") or {}).get("statusDistribution") or []}
    return {
        "_id": f"anilist:{media['id']}", "anilist_id": media["id"], "mal_id": media["idMal"],
        "format": media["format"], "status": media["status"], "episodes": media["episodes"],
        "duration_min": media["duration"], "source_material": media["source"], "country": media["countryOfOrigin"],
        "is_adult": media["isAdult"], "genres": media["genres"], "start_year": (media.get("startDate") or {}).get("year"),
        "average_score": media["averageScore"], "popularity": media["popularity"],
        "status_distribution": distribution, "drop_share": drop_share(distribution),
    }


def unmapped_doc(mal_id):
    return {"_id": f"mal:{mal_id}", "mal_id": mal_id, "reason": "no AniList entry for this MAL id"}


def fetch_chunk(ids, by_mal_id, per_page=PER_PAGE, before_request=None):
    """All media rows for one chunk of ids (the shared pagination helper; stops as soon as every id is answered)."""
    name, text = ("malIds", QUERY_BY_MAL_ID) if by_mal_id else ("ids", QUERY_BY_ANILIST_ID)
    return anilist.collect_pages(
        text, {name: ids, "perPage": per_page}, lambda data: data["Page"]["media"], per_page, max_pages=3, before_request=before_request,
        is_complete=lambda rows: len(rows) >= len(ids))


def split_answer(ids, rows, by_mal_id):
    """(documents for the ids AniList knows, unmapped docs for the MAL ids it does not)."""
    docs = [to_model_b_anime_doc(media) for media in rows]
    if not by_mal_id:
        return docs, []
    answered = {doc["mal_id"] for doc in docs}
    return docs, [unmapped_doc(i) for i in ids if i not in answered]
