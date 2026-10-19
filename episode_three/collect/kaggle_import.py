"""Turn the local Kaggle sample into Model B training documents. Pure functions: no database, no network.

Steps (TASK 016): keep a row only if its MAL id maps to EXACTLY ONE AniList TV, non-adult anime; keep users with at
least 20 remaining entries; split the users 70/15/15 (no user in two splits); split each user's entries into history
(features) and target (rows to predict). A stored entry holds only anime_id, mal_id, status and role: never the episodes
watched or the rating, which describe the outcome on the same row.
"""
import math
from collections import defaultdict

import numpy as np
import pandas as pd

SEED = 42
MIN_ENTRIES = 20
STATUS_NAME = {2: "completed", 4: "dropped"}
SPLIT_FRACTIONS = (0.70, 0.15)            # train, validation; test is the rest
TARGET_FRACTION = 0.2
ENTRY_KEYS = ("anime_id", "mal_id", "status", "role")
# Row-level reasons first, then the anime-level reasons, in funnel order.
REASONS = ("bad_status_code", "duplicate_pair", "unmapped", "ambiguous_mapping", "format_unknown", "format_not_tv", "adult")


# --- The anime map and the row filters ----------------------------------------------------------------------------

def classify_anime(docs, unmapped_mal_ids):
    """{mal id: {"reason": None or an exclusion reason, "sub": detail, "anilist_id": id}} from model_b_anime documents.

    Exactly one document per MAL id is required: two documents (a series AniList split) is ambiguous_mapping, and
    a MAL id in model_b_unmapped is unmapped. A row is kept only when the reason is None.
    """
    by_mal = defaultdict(list)
    for doc in docs:
        if doc.get("mal_id") is not None:
            by_mal[doc["mal_id"]].append(doc)
    result = {}
    for mal_id, found in by_mal.items():
        if len(found) > 1:
            result[mal_id] = {"reason": "ambiguous_mapping", "sub": None, "anilist_id": None}
            continue
        doc = found[0]
        if doc.get("format") is None:
            reason, sub = "format_unknown", None
        elif doc["format"] != "TV":
            reason, sub = "format_not_tv", doc["format"]
        elif doc.get("is_adult"):
            reason, sub = "adult", None
        else:
            reason, sub = None, None
        result[mal_id] = {"reason": reason, "sub": sub, "anilist_id": doc["anilist_id"]}
    for mal_id in unmapped_mal_ids:
        result.setdefault(mal_id, {"reason": "unmapped", "sub": None, "anilist_id": None})
    return result


def apply_filters(rows, anime_map):
    """Filter the sample rows. Returns (kept DataFrame, funnel).

    rows: DataFrame(user_id, anime_id, watching_status) with MAL ids. kept has user_id, mal_id, anilist_id, status
    ("completed" | "dropped"). funnel is a list, one dict per reason in REASONS order:
    {"reason", "rows_removed", "rows_after", "subs": {detail: count}}. A row is counted under the FIRST reason it fails.
    A MAL id found in neither model_b_anime nor model_b_unmapped is counted as unmapped (sub "not_fetched").
    """
    df = rows[["user_id", "anime_id", "watching_status"]].copy()
    funnel = []

    def record(reason, removed_mask, subs):
        funnel.append({"reason": reason, "rows_removed": int(removed_mask.sum()), "subs": dict(sorted(subs.items()))})

    bad = ~df["watching_status"].isin(STATUS_NAME)
    record("bad_status_code", bad, df.loc[bad, "watching_status"].astype(str).value_counts().to_dict())
    df = df[~bad]
    duplicate = df.duplicated(["user_id", "anime_id"], keep="first")     # the first row of a pair is kept
    record("duplicate_pair", duplicate, {})
    df = df[~duplicate]

    reason = df["anime_id"].map(lambda i: anime_map.get(i, {}).get("reason", "unmapped") if i in anime_map else "unmapped")
    sub = df["anime_id"].map(lambda i: anime_map[i]["sub"] if i in anime_map else "not_fetched")
    for name in REASONS[2:]:
        mask = reason == name
        record(name, mask, {k: int(v) for k, v in sub[mask].dropna().value_counts().items()})
    ok = reason.isna()
    df, kept_anilist = df[ok], df.loc[ok, "anime_id"].map(lambda i: anime_map[i]["anilist_id"])
    kept = pd.DataFrame({"user_id": df["user_id"].astype(int), "mal_id": df["anime_id"].astype(int),
                         "anilist_id": kept_anilist.astype(int), "status": df["watching_status"].map(STATUS_NAME)})
    remaining = len(rows)
    for step in funnel:
        remaining -= step["rows_removed"]
        step["rows_after"] = remaining
    assert remaining == len(kept), "the funnel does not add up"
    return kept.reset_index(drop=True), funnel


def filter_users(kept, min_entries=MIN_ENTRIES):
    """Keep users with at least min_entries remaining entries. Returns (kept, users_removed, rows_removed)."""
    counts = kept.groupby("user_id").size()
    small = counts[counts < min_entries].index
    drop = kept["user_id"].isin(small)
    return kept[~drop].reset_index(drop=True), int(len(small)), int(drop.sum())


# --- Splits --------------------------------------------------------------------------------------------------------------

def split_users(user_ids, seed=SEED):
    """{user_id: "train" | "validation" | "test"}: sort the unique ids, permute with default_rng(seed), slice 70/15/15.

    Each user lands in exactly one split. Sizes use round() for train and validation; test gets the rest.
    """
    ids = np.array(sorted({int(u) for u in user_ids}))
    permuted = ids[np.random.default_rng(seed).permutation(len(ids))]
    n_train = int(round(SPLIT_FRACTIONS[0] * len(ids)))
    n_validation = int(round(SPLIT_FRACTIONS[1] * len(ids)))
    names = ["train"] * n_train + ["validation"] * n_validation + ["test"] * (len(ids) - n_train - n_validation)
    return {int(u): name for u, name in zip(permuted, names)}


def target_count(n_entries):
    """How many of a user's entries are targets: max(1, floor(0.2 * n))."""
    return max(1, math.floor(TARGET_FRACTION * n_entries))


def split_history_target(anime_ids, user_id, seed=SEED):
    """{anime_id: "history" | "target"} for one user.

    The generator is seeded from (seed, user_id), so a user's roles never change when other users are added or
    removed, and do not depend on the order the entries arrive in (they are sorted first).
    """
    ordered = sorted(anime_ids)
    n_target = target_count(len(ordered))
    chosen = set(np.random.default_rng([seed, int(user_id)]).permutation(len(ordered))[:n_target].tolist())
    return {anime_id: ("target" if i in chosen else "history") for i, anime_id in enumerate(ordered)}


def to_user_doc(user_id, split, entries):
    """One mal_user_lists document. entries: [{"anilist_id", "mal_id", "status", "role"}].

    Only anime_id ("anilist:<id>"), mal_id, status and role are stored; entries are sorted for a stable document.
    """
    stored = sorted(({"anime_id": f"anilist:{e['anilist_id']}", "mal_id": int(e["mal_id"]), "status": e["status"], "role": e["role"]}
                     for e in entries), key=lambda e: e["mal_id"])
    n_target = sum(1 for e in stored if e["role"] == "target")
    return {"_id": f"mal_user:{int(user_id)}", "split": split, "n_entries": len(stored),
            "n_history": len(stored) - n_target, "n_target": n_target, "entries": stored}


def build_documents(kept, seed=SEED):
    """All user documents from the filtered entries (users already filtered to >= 20 entries). Deterministic."""
    splits = split_users(kept["user_id"].unique(), seed)
    docs = []
    for user_id, group in kept.sort_values(["user_id", "mal_id"]).groupby("user_id", sort=True):
        roles = split_history_target(group["mal_id"].tolist(), user_id, seed)
        entries = [{"anilist_id": a, "mal_id": m, "status": s, "role": roles[m]}
                   for a, m, s in zip(group["anilist_id"], group["mal_id"], group["status"])]
        docs.append(to_user_doc(user_id, splits[int(user_id)], entries))
    return docs


# --- The report --------------------------------------------------------------------------------------------------------------

def split_statistics(docs):
    """Per split: users, history rows, target rows, target drop rate, entries per user (min / median / max)."""
    stats = {}
    for name in ("train", "validation", "test"):
        part = [d for d in docs if d["split"] == name]
        sizes = sorted(d["n_entries"] for d in part)
        targets = [e for d in part for e in d["entries"] if e["role"] == "target"]
        stats[name] = {
            "users": len(part), "history_rows": sum(d["n_history"] for d in part), "target_rows": len(targets),
            "target_drop_rate": (sum(1 for e in targets if e["status"] == "dropped") / len(targets)) if targets else None,
            "entries_min": sizes[0] if sizes else None, "entries_median": float(np.median(sizes)) if sizes else None,
            "entries_max": sizes[-1] if sizes else None}
    return stats


def funnel_markdown(total_rows, total_users, funnel, users_removed, rows_by_small_users, docs, nirav):
    """The Model B data funnel as Markdown (deterministic: no timestamps, no database sizes)."""
    lines = ["# Model B data funnel", "", "Generated by `python -m scripts.import_kaggle_users`. Deterministic: no timestamps.",
             "", "## Rows and users at each step", "", "| Step | Rows removed | Rows left |", "|---|---:|---:|",
             f"| sample (completed/dropped rows of 5,000 users, MAL type TV) | | {total_rows:,} |"]
    for step in funnel:
        detail = (" (" + ", ".join(f"{k}: {v:,}" for k, v in step["subs"].items()) + ")") if step["subs"] else ""
        lines.append(f"| {step['reason']}{detail} | {step['rows_removed']:,} | {step['rows_after']:,} |")
    after_filters = funnel[-1]["rows_after"]
    kept_rows = sum(d["n_entries"] for d in docs)
    lines += [f"| users with fewer than {MIN_ENTRIES} entries left ({users_removed:,} users) | {rows_by_small_users:,} | {kept_rows:,} |", "",
              f"Users: {total_users:,} in the sample, {len(docs):,} kept ({users_removed:,} fell below {MIN_ENTRIES} entries after the AniList-TV filter). "
              f"Rows after the row filters: {after_filters:,}; rows kept: {kept_rows:,}.", "",
              "## Per split (users are split 70/15/15 by user id; each user is in exactly one split)", "",
              "| Split | Users | History rows | Target rows | Target drop rate | Entries per user (min / median / max) |",
              "|---|---:|---:|---:|---:|---|"]
    for name, s in split_statistics(docs).items():
        rate = "-" if s["target_drop_rate"] is None else f"{100 * s['target_drop_rate']:.2f}%"
        sizes = "-" if s["entries_min"] is None else f"{s['entries_min']} / {s['entries_median']:g} / {s['entries_max']}"
        lines.append(f"| {name} | {s['users']:,} | {s['history_rows']:,} | {s['target_rows']:,} | {rate} | {sizes} |")
    lines += ["", "## Nirav under the same filter (AniList TV, non-adult, completed vs dropped, REPEATING = completed)", "",
              f"- Labelled entries: **{nirav['labelled']:,}**, dropped {nirav['dropped']:,} (**{100 * nirav['drop_rate']:.1f}%**).",
              f"- Of those, {nirav['mal_non_tv']:,} are typed non-TV by MAL (" + ", ".join(f"{k} {v}" for k, v in nirav["mal_non_tv_types"].items())
              + f"); {nirav['not_in_2020_csv']:,} are too new for the 2020 file to say. He is not stored in `mal_user_lists`; his features come from `my_entries`.", "",
              "## Disclosures", "",
              "- The 5,000-user sample was drawn under the MAL TV definition (and required 20+ MAL-TV entries). Re-filtering to AniList TV afterwards "
              "leaves some users with fewer entries; those below 20 are dropped and the sample is **not** redrawn.",
              "- AniList TV excludes AniList's TV_SHORT format (MAL calls most of those TV). Training and Nirav's side use the same definition.",
              "- Rows are never stored with episodes watched or ratings (same-row leakage); the stored entry is anime_id, mal_id, status, role.",
              "- History/target roles use a generator seeded from (42, user id): a user's roles do not change when other users change.", ""]
    return "\n".join(lines)
