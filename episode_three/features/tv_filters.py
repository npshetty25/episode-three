"""How much do the "MAL TV" and "AniList TV" definitions differ? Pure functions; 0 requests.

The Kaggle sample was filtered on MAL Type = TV. Model B will use AniList format = TV on both sides (spec v1.6 ruling 4),
so we measure the gap first. Inputs are plain frames/dicts; scripts/compare_tv_filters.py reads the files and the database.
"""
import numpy as np
import pandas as pd

MIN_ENTRIES = 20            # the training-user rule: at least 20 completed/dropped rows
COMPLETED, DROPPED = 2, 4
UNMAPPED = "(no AniList record)"


def _users_kept(frame, min_entries):
    counts = frame.groupby("user_id").size()
    return int((counts >= min_entries).sum()), int(len(counts))


def filter_scenarios(sample, anilist_format_by_mal, mal_type_by_mal, min_entries=MIN_ENTRIES):
    """Rows, anime and users kept under (i) MAL TV, (ii) AniList TV, (iii) both. Users are kept at >= min_entries rows.

    sample: DataFrame(user_id, anime_id, watching_status); anilist_format_by_mal: {mal id: AniList format}, a missing id is
    unmapped (treated as not TV); mal_type_by_mal: {mal id: MAL Type}.
    """
    anilist_tv = sample["anime_id"].map(lambda i: anilist_format_by_mal.get(i) == "TV")
    mal_tv = sample["anime_id"].map(lambda i: mal_type_by_mal.get(i) == "TV")
    result = {}
    for name, mask in (("i_mal_tv", mal_tv), ("ii_anilist_tv", anilist_tv), ("iii_both", mal_tv & anilist_tv)):
        kept = sample[mask]
        users_ok, users_with_rows = _users_kept(kept, min_entries)
        result[name] = {"rows": int(len(kept)), "anime": int(kept["anime_id"].nunique()),
                        "users_with_rows": users_with_rows, "users_kept": users_ok,
                        "users_below_min": int(sample["user_id"].nunique()) - users_ok,
                        "drop_rate": float((kept["watching_status"] == DROPPED).mean()) if len(kept) else None}
    return result


def mal_tv_by_anilist_format(sample, anilist_format_by_mal):
    """For the sample's MAL-TV anime: how many anime and rows fall under each AniList format (or unmapped)."""
    per_anime = sample.groupby("anime_id").size()
    anime, rows = {}, {}
    for mal_id, count in per_anime.items():
        fmt = anilist_format_by_mal.get(mal_id) or UNMAPPED
        anime[fmt], rows[fmt] = anime.get(fmt, 0) + 1, rows.get(fmt, 0) + int(count)
    return {"anime": dict(sorted(anime.items(), key=lambda kv: -kv[1])), "rows": dict(sorted(rows.items(), key=lambda kv: -kv[1]))}


def coverage(sample, docs_by_mal):
    """Share of sample rows (and anime) whose anime has an AniList record / a usable drop_share (completed + dropped > 0)."""
    has = sample["anime_id"].map(lambda i: i in docs_by_mal)
    usable = sample["anime_id"].map(lambda i: docs_by_mal.get(i, {}).get("drop_share") is not None)
    anime = sample["anime_id"].drop_duplicates()
    return {"rows": int(len(sample)), "rows_with_record": int(has.sum()), "rows_with_drop_share": int(usable.sum()),
            "anime": int(len(anime)), "anime_with_record": int(anime.map(lambda i: i in docs_by_mal).sum()),
            "anime_with_drop_share": int(anime.map(lambda i: docs_by_mal.get(i, {}).get("drop_share") is not None).sum())}


def unknown_episode_tv(anime_csv, docs_by_mal):
    """MAL TV anime whose episode count is unknown in anime.csv: how many have episodes on AniList now (if fetched)."""
    unknown = anime_csv[(anime_csv["Type"] == "TV") & anime_csv["Episodes"].isna()]
    ids = [int(i) for i in unknown["MAL_ID"]]
    fetched = [i for i in ids if i in docs_by_mal]
    return {"mal_tv_unknown_episodes": len(ids), "fetched": len(fetched),
            "with_episodes_on_anilist": sum(1 for i in fetched if docs_by_mal[i].get("episodes")),
            "not_fetched": len(ids) - len(fetched), "ids_not_fetched": [i for i in ids if i not in docs_by_mal]}


def nirav_comparison(entries, titles_by_id, mal_type_by_mal, labelled_entries, drop_rate):
    """Nirav's labelled TV entries under AniList TV, and how many are MAL non-TV (or not in the 2020 anime.csv)."""
    kept = labelled_entries(entries, titles_by_id, formats=("TV",))
    non_tv, unknown = [], []
    for entry in kept:
        title = titles_by_id[entry["title_id"]]
        mal_type = mal_type_by_mal.get(title.get("mal_id"))
        if mal_type is None or pd.isna(mal_type):        # not in anime.csv, or MAL left the type blank
            unknown.append(entry)
        elif mal_type != "TV":
            non_tv.append(entry)
    types = {}
    for entry in non_tv:
        t = mal_type_by_mal[titles_by_id[entry["title_id"]]["mal_id"]]
        types[t] = types.get(t, 0) + 1
    return {"labelled": len(kept), "dropped": sum(1 for e in kept if e["mal_status_code"] == DROPPED), "drop_rate": drop_rate(kept),
            "mal_non_tv": len(non_tv), "mal_non_tv_types": dict(sorted(types.items(), key=lambda kv: -kv[1])),
            "not_in_2020_csv": len(unknown), "non_tv_mal_ids": sorted({titles_by_id[e["title_id"]]["mal_id"] for e in non_tv})}


def count_rows_for_ids(csv_path, ids, chunk_rows=5_000_000):
    """Completed/dropped rows of the given MAL ids in the FULL animelist.csv, read in chunks (0 requests)."""
    ids = set(int(i) for i in ids)
    per_anime, users, total_rows = {}, set(), 0
    for chunk in pd.read_csv(csv_path, usecols=["user_id", "anime_id", "watching_status"], chunksize=chunk_rows,
                             dtype={"user_id": np.int64, "anime_id": np.int64, "watching_status": np.int8}):
        total_rows += len(chunk)
        hit = chunk[chunk["anime_id"].isin(ids) & chunk["watching_status"].isin((COMPLETED, DROPPED))]
        for anime_id, n in hit.groupby("anime_id").size().items():
            per_anime[int(anime_id)] = per_anime.get(int(anime_id), 0) + int(n)
        users.update(hit["user_id"].unique().tolist())
    return {"file_rows": total_rows, "rows": sum(per_anime.values()), "anime_with_rows": len(per_anime),
            "users": len(users), "per_anime": per_anime}


def extra_mapping_requests(all_mal_ids, fetched_mal_ids, per_page=50):
    """Requests needed to learn the AniList format of every MAL anime we have not fetched yet."""
    missing = len(set(all_mal_ids) - set(fetched_mal_ids))
    return missing, -(-missing // per_page)
