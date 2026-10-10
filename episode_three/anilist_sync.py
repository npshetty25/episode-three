"""Copy Nirav's PUBLIC AniList anime list into MongoDB (read-only).

AniList is Nirav's tracker and the source of truth. AniList's terms (clause 5)
forbid using the API to run a competing list/tracker service, so this app is a
dashboard ON TOP of AniList: it only reads one user's own list, never writes to
AniList, and stores only the fields the app uses.

Safe to re-run: every document has a fixed _id, documents are only written when
their content changed, and entries removed on AniList are removed here too.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone

from pymongo import UpdateOne

from episode_three.clients import anilist

PER_CHUNK = 500  # AniList's maximum entries per chunk

# The whole list in one query (split into chunks only if it has more than 500 entries).
LIST_QUERY = """
query ($userName: String, $chunk: Int, $perChunk: Int) {
  MediaListCollection(userName: $userName, type: ANIME, forceSingleCompletedList: true,
                      chunk: $chunk, perChunk: $perChunk) {
    hasNextChunk
    user { id name mediaListOptions { scoreFormat } }
    lists {
      name isCustomList status
      entries {
        id mediaId status progress repeat score(format: POINT_100) private hiddenFromStatusLists
        startedAt { year month day } completedAt { year month day } createdAt updatedAt
        media {
          id idMal title { romaji english native } format status episodes duration season seasonYear
          startDate { year month day } endDate { year month day } genres source isAdult
          averageScore meanScore popularity siteUrl coverImage { large }
        }
      }
    }
  }
}"""

# AniList status -> the MyAnimeList code used in Model B's training data.
# REPEATING (rewatching) counts as Completed, with a separate repeating flag.
STATUS_TO_MAL_CODE = {"CURRENT": 1, "COMPLETED": 2, "REPEATING": 2, "PAUSED": 3, "DROPPED": 4, "PLANNING": 6}

# Origin rule. Nirav imported his old MyAnimeList list into AniList on 2026-10-08:
# all 139 imported entries have createdAt 08:57:54 UTC (to the second).
# Entries created before this cutoff came from that import; later ones were added on AniList.
MAL_IMPORT_CUTOFF = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)

STALE_AFTER_DAYS = 180

# An imported entry still counts as untouched if it was updated within this many seconds of
# its creation. After Nirav edits it on AniList, updated_at moves later and it leaves the report.
IMPORT_EDIT_GRACE_SECONDS = 60


# --- Fetching --------------------------------------------------------------

def fetch_list(username):
    """Download the user's whole anime list. Returns a list of chunk answers (usually one)."""
    chunks = []
    chunk = 1
    while True:
        try:
            data = anilist.post_query(LIST_QUERY, {"userName": username, "chunk": chunk, "perChunk": PER_CHUNK})
        except anilist.AniListError as error:
            # AniList answers HTTP 404 "User not found" (with data.MediaListCollection = null).
            if "user not found" in str(error).lower():
                raise anilist.AniListError(
                    f"AniList has no user named '{username}'. Check ANILIST_USERNAME in .env "
                    "(it is the name in your profile link, anilist.co/user/<name>)."
                ) from None
            raise
        collection = data["MediaListCollection"]
        if collection is None:
            raise anilist.AniListError(f"AniList returned no list for '{username}' (is the list private?).")
        chunks.append(collection)
        if not collection.get("hasNextChunk"):
            return chunks
        chunk += 1


def unique_entries(chunks):
    """All entries, each once. An entry in both a status list and a custom list appears twice."""
    seen = {}
    for collection in chunks:
        for one_list in collection["lists"]:
            for entry in one_list["entries"]:
                seen.setdefault(entry["id"], entry)
    return list(seen.values())


# --- Converting AniList answers into our documents --------------------------

def fuzzy_date(value):
    """AniList's {year, month, day} (any part may be null) -> the same dict, or None if all null."""
    if not value or all(value.get(part) is None for part in ("year", "month", "day")):
        return None
    return {"year": value.get("year"), "month": value.get("month"), "day": value.get("day")}


def unix_to_datetime(seconds):
    """Unix seconds -> a UTC datetime (None stays None)."""
    if seconds is None:
        return None
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def entry_origin(created_at_seconds, cutoff=MAL_IMPORT_CUTOFF):
    """'mal_import' if the entry was created before the import cutoff, else 'anilist'."""
    if not created_at_seconds or unix_to_datetime(created_at_seconds) < cutoff:
        return "mal_import"
    return "anilist"


def to_entry_doc(entry, username, changed_at):
    """One AniList list entry -> one my_entries document.

    `changed_at` is stored as content_changed_at. It is only written when the
    content really changed (see plan_changes), so it means "last real change".
    """
    status = entry["status"]
    if status not in STATUS_TO_MAL_CODE:
        raise ValueError(f"Unknown AniList status {status!r} on entry {entry['id']}")
    return {
        "_id": f"anilist_entry:{entry['id']}",
        "source": "anilist",  # the sync may only ever delete documents with this source
        "username": username,
        "title_id": f"anilist:{entry['mediaId']}",
        "anilist_status": status,
        "mal_status_code": STATUS_TO_MAL_CODE[status],
        "repeating": status == "REPEATING",
        "progress": entry["progress"],
        "score_100": entry["score"] or None,  # 0 means "not scored"
        "started_at": fuzzy_date(entry["startedAt"]),
        "completed_at": fuzzy_date(entry["completedAt"]),
        "created_at": unix_to_datetime(entry["createdAt"]),
        "updated_at": unix_to_datetime(entry["updatedAt"]),
        "origin": entry_origin(entry["createdAt"]),
        "content_changed_at": changed_at,
    }


def to_title_doc(media, changed_at):
    """AniList media -> one titles document (only fields the app uses; no stats yet)."""
    return {
        "_id": f"anilist:{media['id']}",
        "source": "anilist",
        "media_type": "anime",
        "anilist_id": media["id"],
        "mal_id": media["idMal"],
        "title": media["title"],
        "format": media["format"],
        "status": media["status"],
        "episodes": media["episodes"],
        "duration_min": media["duration"],
        "season": media["season"],
        "season_year": media["seasonYear"],
        "start_date": fuzzy_date(media["startDate"]),
        "end_date": fuzzy_date(media["endDate"]),
        "genres": media["genres"],
        "source_material": media["source"],
        "is_adult": media["isAdult"],
        "current_average_score": media["averageScore"],
        "current_mean_score": media["meanScore"],
        "current_popularity": media["popularity"],
        "site_url": media["siteUrl"],
        "cover_url": (media.get("coverImage") or {}).get("large"),
        "content_changed_at": changed_at,
    }


# --- Working out what to write ---------------------------------------------

def without_change_time(doc):
    return {key: value for key, value in doc.items() if key != "content_changed_at"}


def stored_entries_filter(username):
    """Which my_entries documents belong to this user's AniList sync.

    my_entries also holds hand-entered TV/movie entries (source "manual"); they must
    never be compared against AniList, or deleted because AniList doesn't list them.
    """
    return {"source": "anilist", "username": username}


def entry_deletion_filter(username, removed_ids):
    """The ONLY filter the sync deletes with: listed _ids, and only AniList entries of this user."""
    return {"_id": {"$in": list(removed_ids)}, **stored_entries_filter(username)}


def plan_changes(stored_docs, fresh_docs):
    """Compare fresh documents with the stored ones (ignoring content_changed_at).

    Returns which documents are new, which changed, which are unchanged, and which
    stored _ids are no longer in the fresh data.
    """
    stored = {doc["_id"]: doc for doc in stored_docs}
    plan = {"new": [], "changed": [], "unchanged": [], "removed": []}
    for doc in fresh_docs:
        old = stored.get(doc["_id"])
        if old is None:
            plan["new"].append(doc)
        elif without_change_time(old) != without_change_time(doc):
            plan["changed"].append(doc)
        else:
            plan["unchanged"].append(doc["_id"])
    fresh_ids = {doc["_id"] for doc in fresh_docs}
    plan["removed"] = sorted(_id for _id in stored if _id not in fresh_ids)
    return plan


def write_changes(collection, plan, delete_filter=None):
    """Write new and changed documents in one batch; delete removed ones only with `delete_filter`."""
    to_write = plan["new"] + plan["changed"]
    inserted = modified = deleted = 0
    if to_write:
        operations = [UpdateOne({"_id": doc["_id"]},
                                {"$set": {k: v for k, v in doc.items() if k != "_id"}},
                                upsert=True)
                      for doc in to_write]
        result = collection.bulk_write(operations, ordered=False)
        inserted, modified = result.upserted_count, result.modified_count
    if delete_filter is not None and plan["removed"]:
        deleted = collection.delete_many(delete_filter).deleted_count
    return {"inserted": inserted, "modified": modified, "unchanged": len(plan["unchanged"]), "deleted": deleted}


# --- The sync --------------------------------------------------------------

def sync(db, username, chunks=None):
    """Sync one user's list into db. Pass `chunks` to reuse an earlier fetch (no request)."""
    started_at = datetime.now(timezone.utc)
    requests_before = anilist.stats["requests"]
    if chunks is None:
        chunks = fetch_list(username)

    entries = unique_entries(chunks)
    entry_docs = [to_entry_doc(entry, username, started_at) for entry in entries]
    title_docs = list({doc["_id"]: doc for doc in
                       (to_title_doc(entry["media"], started_at) for entry in entries)}.values())

    entry_plan = plan_changes(db["my_entries"].find(stored_entries_filter(username)), entry_docs)
    title_plan = plan_changes(db["titles"].find({"_id": {"$in": [doc["_id"] for doc in title_docs]}}), title_docs)

    # AniList is the truth for anime: AniList entries gone from AniList are deleted,
    # and nothing else can match the deletion filter. Titles are kept (no personal data).
    entry_counts = write_changes(db["my_entries"], entry_plan,
                                 delete_filter=entry_deletion_filter(username, entry_plan["removed"]))
    title_counts = write_changes(db["titles"], title_plan)

    counts = {
        "fetched": len(entry_docs),
        **entry_counts,
        "by_status": dict(sorted(Counter(doc["anilist_status"] for doc in entry_docs).items())),
        "titles": {"fetched": len(title_docs), **{k: v for k, v in title_counts.items() if k != "deleted"}},
    }
    finished_at = datetime.now(timezone.utc)
    db["sync_runs"].insert_one({
        "_id": f"sync:anilist:{started_at.strftime('%Y-%m-%dT%H:%M:%S.%fZ')}",
        "job": "anilist_list",
        "username": username,
        "started_at": started_at,
        "finished_at": finished_at,
        "requests_used": anilist.stats["requests"] - requests_before,
        "counts": counts,
    })
    counts["requests_used"] = anilist.stats["requests"] - requests_before
    return counts


# --- Reports ---------------------------------------------------------------

def untouched_import(doc):
    """True for an imported entry that has not been edited on AniList since the import."""
    if doc["origin"] != "mal_import":
        return False
    created, updated = doc["created_at"], doc["updated_at"]
    if created is None or updated is None:
        return True
    return (updated - created).total_seconds() <= IMPORT_EDIT_GRACE_SECONDS


def stale_entries(entry_docs, titles_by_id, now, days=STALE_AFTER_DAYS):
    """CURRENT/PAUSED entries that are untouched imports, or not updated for `days` days."""
    cutoff = now - timedelta(days=days)
    stale = []
    for doc in entry_docs:
        if doc["anilist_status"] not in ("CURRENT", "PAUSED"):
            continue
        old = doc["updated_at"] is not None and doc["updated_at"] < cutoff
        if untouched_import(doc) or old:
            title = titles_by_id.get(doc["title_id"], {})
            names = title.get("title") or {}
            stale.append({
                "title": names.get("english") or names.get("romaji") or doc["title_id"],
                "status": doc["anilist_status"],
                "progress": doc["progress"],
                "episodes": title.get("episodes"),
                "origin": doc["origin"],
                "updated_at": doc["updated_at"],
                "reason": "imported, not edited since" if untouched_import(doc) else f"not updated in {days} days",
            })
    return sorted(stale, key=lambda row: (row["status"], row["title"].lower()))


def count_without_dates(entry_docs):
    """How many entries have no started_at and no completed_at."""
    return sum(1 for doc in entry_docs if doc["started_at"] is None and doc["completed_at"] is None)
