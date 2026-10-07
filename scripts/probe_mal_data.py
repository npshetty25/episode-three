"""Probe: can the Kaggle MyAnimeList 2020 data feed Model B? (TASK 004)

Run from the episode-three folder (either form works):
    python scripts\\probe_mal_data.py
    python -m scripts.probe_mal_data

What it does:
1. Checks the CSV files, their headers, and the watching-status codes.
2. Decides which anime are eligible (TV, not adult, at least 2 episodes).
3. Streams the 1.9 GB animelist.csv in chunks (it never fits in memory at once)
   and counts, per user, their completed-or-dropped entries for eligible anime.
4. Samples 5,000 users with seed 42 and saves their rows to
   data/processed/ (git-ignored), then prints the numbers Model B depends on.
"""
import sys
import time
from pathlib import Path

# Lets "python scripts\probe_mal_data.py" find the episode_three package
# (running a file directly only puts the scripts folder on Python's path).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from episode_three import config

SEED = 42
SAMPLE_SIZE = 5_000
MIN_LABELED_ENTRIES = 20
CHUNK_ROWS = 2_000_000
COMPLETED, DROPPED = 2, 4
LABEL_STATUSES = [COMPLETED, DROPPED]

EXPECTED_STATUS_CODES = {1: "Currently Watching", 2: "Completed", 3: "On Hold", 4: "Dropped", 6: "Plan to Watch"}
EXPECTED_ANIMELIST_COLUMNS = ["user_id", "anime_id", "rating", "watching_status", "watched_episodes"]
EXPECTED_ANIME_COLUMNS = (
    ["MAL_ID", "Name", "Score", "Genres", "English name", "Japanese name", "Type", "Episodes", "Aired",
     "Premiered", "Producers", "Licensors", "Studios", "Source", "Duration", "Rating", "Ranked", "Popularity",
     "Members", "Favorites", "Watching", "Completed", "On-Hold", "Dropped", "Plan to Watch"]
    + [f"Score-{n}" for n in range(10, 0, -1)]
)
# Small integer types: a 2-million-row chunk takes ~28 MB instead of ~80 MB with default int64.
ANIMELIST_DTYPES = {"user_id": "int32", "anime_id": "int32", "rating": "int8",
                    "watching_status": "int8", "watched_episodes": "int32"}

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
SAMPLE_PATH = OUTPUT_DIR / f"mal_sample_5k_seed{SEED}.parquet"
USER_IDS_PATH = OUTPUT_DIR / f"sample_user_ids_seed{SEED}.csv"


# --- Pure helpers (tested in tests/test_probe_helpers.py) -------------------

def genre_list(genres):
    """'Action, Hentai' -> ['Action', 'Hentai']; missing -> []."""
    if not isinstance(genres, str):
        return []
    return [g.strip() for g in genres.split(",")]


def eligible_anime_ids(anime):
    """MAL IDs of anime Model B may use: TV, not Hentai, not Rx-rated, at least 2 known episodes."""
    is_tv = anime["Type"] == "TV"
    is_hentai = anime["Genres"].apply(lambda g: "Hentai" in genre_list(g))
    is_rx = anime["Rating"].fillna("").str.startswith("Rx")
    enough_episodes = anime["Episodes"].notna() & (anime["Episodes"] >= 2)
    keep = is_tv & ~is_hentai & ~is_rx & enough_episodes
    return set(anime.loc[keep, "MAL_ID"].astype(int))


def labeled_rows(chunk, eligible_ids):
    """Rows for eligible anime whose status is Completed or Dropped (Model B's labels)."""
    mask = chunk["anime_id"].isin(eligible_ids) & chunk["watching_status"].isin(LABEL_STATUSES)
    return chunk[mask]


def count_labeled_per_user(chunk, eligible_ids):
    """How many labeled rows each user has in this chunk (a pandas Series: user_id -> count)."""
    return labeled_rows(chunk, eligible_ids)["user_id"].value_counts()


def sample_users(labeled_counts, min_entries=MIN_LABELED_ENTRIES, size=SAMPLE_SIZE, seed=SEED):
    """Pick `size` users with at least `min_entries` labeled rows, reproducibly.

    The candidates are sorted first, so the result depends only on the data and
    the seed, never on the order the counts happened to be built in.
    """
    eligible = np.sort(labeled_counts[labeled_counts >= min_entries].index.to_numpy())
    rng = np.random.default_rng(seed)
    chosen = rng.choice(eligible, size=min(size, len(eligible)), replace=False)
    return np.sort(chosen), len(eligible)


def drop_rate_summary(sample):
    """Completed vs dropped numbers for the sample (one row per user-anime pair)."""
    is_dropped = sample["watching_status"] == DROPPED
    per_user = is_dropped.groupby(sample["user_id"]).mean()
    entries = sample.groupby("user_id").size()
    return {
        "rows": len(sample),
        "completed": int((sample["watching_status"] == COMPLETED).sum()),
        "dropped": int(is_dropped.sum()),
        "drop_rate": float(is_dropped.mean()),
        "user_drop_rate_quantiles": {q: float(per_user.quantile(q)) for q in (0, 0.25, 0.5, 0.75, 1)},
        "share_users_no_drops": float((per_user == 0).mean()),
        "share_users_all_drops": float((per_user == 1).mean()),
        "entries_per_user": {"min": int(entries.min()), "median": float(entries.median()), "max": int(entries.max())},
        "distinct_anime": int(sample["anime_id"].nunique()),
    }


# --- Steps -----------------------------------------------------------------

def show_files(data_dir):
    print("Files in MAL_DATA_DIR:")
    for path in sorted(data_dir.glob("*")):
        print(f"  {path.name:<28} {path.stat().st_size / 1024 / 1024:9.1f} MB")


def check_headers(data_dir, problems):
    """Print each CSV's header and first 3 rows; compare two of them with the verified facts."""
    expected = {"animelist.csv": EXPECTED_ANIMELIST_COLUMNS, "anime.csv": EXPECTED_ANIME_COLUMNS}
    for name in ["animelist.csv", "anime.csv", "anime_with_synopsis.csv", "rating_complete.csv", "watching_status.csv"]:
        head = pd.read_csv(data_dir / name, nrows=3, encoding="utf-8")
        print(f"\n{name}: {len(head.columns)} columns")
        print("  " + ", ".join(head.columns))
        print(head.to_string(index=False, max_colwidth=25))
        if name in expected and list(head.columns) != expected[name]:
            missing = [c for c in expected[name] if c not in head.columns]
            extra = [c for c in head.columns if c not in expected[name]]
            problems.append(f"{name} columns differ from the verified facts (missing {missing}, extra {extra})")
            print(f"  !! differs from verified facts: missing {missing}, extra {extra}")
        elif name in expected:
            print("  matches the verified header")


def check_encoding(data_dir):
    """Is anime.csv valid UTF-8? (Garbled Japanese in a console can be the console, not the file.)"""
    text = (data_dir / "anime.csv").read_bytes().decode("utf-8", errors="strict")
    japanese = sum(1 for ch in text if "぀" <= ch <= "ヿ" or "一" <= ch <= "鿿")
    mojibake = text.count("ã\u0081") + text.count("ã\u0082")
    print(f"\nanime.csv decodes as strict UTF-8: yes. Japanese characters: {japanese:,}; "
          f"typical mojibake sequences: {mojibake}")


def check_status_codes(data_dir, problems):
    codes = pd.read_csv(data_dir / "watching_status.csv", encoding="utf-8")
    codes.columns = [c.strip() for c in codes.columns]
    table = {int(row.iloc[0]): str(row.iloc[1]).strip() for _, row in codes.iterrows()}
    print("\nwatching_status.csv:")
    for code, description in table.items():
        print(f"  {code}: {description}")
    if table != EXPECTED_STATUS_CODES:
        problems.append(f"watching_status.csv differs from the verified codes: {table}")
        print("  !!!! MISMATCH with the verified status codes !!!!")
    else:
        print("  matches the verified codes")
    return table


def inspect_anime(data_dir):
    anime = pd.read_csv(data_dir / "anime.csv", encoding="utf-8", na_values=["Unknown"])
    print(f"\nanime.csv: {len(anime):,} anime")
    print("Type value counts:")
    print(anime["Type"].value_counts(dropna=False).to_string())
    print("Rating values:")
    print(anime["Rating"].value_counts(dropna=False).to_string())
    is_hentai = anime["Genres"].apply(lambda g: "Hentai" in genre_list(g))
    is_rx = anime["Rating"].fillna("").str.startswith("Rx")
    print(f"Hentai-genre rows: {is_hentai.sum():,}; Rx-rated rows: {is_rx.sum():,}; "
          f"both: {(is_hentai & is_rx).sum():,}; Hentai only: {(is_hentai & ~is_rx).sum():,}; "
          f"Rx only: {(is_rx & ~is_hentai).sum():,}")
    tv = anime["Type"] == "TV"
    print(f"Among TV: Hentai {(tv & is_hentai).sum()}, Rx {(tv & is_rx).sum()}, "
          f"episodes unknown {(tv & anime['Episodes'].isna()).sum()}, 1 episode {(tv & (anime['Episodes'] == 1)).sum()}")
    eligible = eligible_anime_ids(anime)
    print(f"Eligible anime (TV, not Hentai, not Rx, >= 2 episodes): {len(eligible):,}")
    return set(anime["MAL_ID"].astype(int)), eligible


def first_pass(path, known_ids, eligible_ids, status_codes):
    """One streaming pass over animelist.csv."""
    total_rows = missing_anime = duplicates_in_chunks = 0
    rows_per_user = pd.Series(dtype="int64")
    labeled_per_user = pd.Series(dtype="int64")
    status_counts = pd.Series(dtype="int64")
    for number, chunk in enumerate(pd.read_csv(path, chunksize=CHUNK_ROWS, dtype=ANIMELIST_DTYPES), 1):
        total_rows += len(chunk)
        missing_anime += int((~chunk["anime_id"].isin(known_ids)).sum())
        duplicates_in_chunks += int(chunk.duplicated(["user_id", "anime_id"]).sum())
        rows_per_user = rows_per_user.add(chunk["user_id"].value_counts(), fill_value=0)
        labeled_per_user = labeled_per_user.add(count_labeled_per_user(chunk, eligible_ids), fill_value=0)
        status_counts = status_counts.add(chunk["watching_status"].value_counts(), fill_value=0)
        print(f"  chunk {number}: {total_rows:,} rows read", flush=True)
    unknown_codes = sorted(int(c) for c in status_counts.index if int(c) not in status_codes)
    return {
        "total_rows": total_rows, "unique_users": len(rows_per_user), "missing_anime_rows": missing_anime,
        "duplicates_in_chunks": duplicates_in_chunks, "status_counts": status_counts.astype(int),
        "unknown_codes": unknown_codes, "labeled_per_user": labeled_per_user.astype(int),
    }


def second_pass(path, user_ids, eligible_ids):
    """Collect the sampled users' labeled rows."""
    kept = []
    for chunk in pd.read_csv(path, chunksize=CHUNK_ROWS, dtype=ANIMELIST_DTYPES):
        rows = labeled_rows(chunk, eligible_ids)
        kept.append(rows[rows["user_id"].isin(user_ids)])
    return pd.concat(kept, ignore_index=True)


def verdict(problems, eligible_users, drop_rate):
    if eligible_users < 2_000:
        return "NO-GO", [f"only {eligible_users:,} eligible users"]
    reasons = list(problems)
    if eligible_users < SAMPLE_SIZE:
        reasons.append(f"{eligible_users:,} eligible users (< {SAMPLE_SIZE:,})")
    if not 0.05 <= drop_rate <= 0.40:
        reasons.append(f"drop rate {drop_rate:.1%} is outside 5-40%")
    return ("PARTIAL" if reasons else "GO"), reasons


def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    started = time.monotonic()
    problems = []
    data_dir = config.get_mal_data_dir()

    show_files(data_dir)
    check_headers(data_dir, problems)
    check_encoding(data_dir)
    status_codes = check_status_codes(data_dir, problems)
    known_ids, eligible_ids = inspect_anime(data_dir)

    print("\nPass 1 over animelist.csv (chunks of 2,000,000 rows):")
    stats = first_pass(data_dir / "animelist.csv", known_ids, eligible_ids, status_codes)
    print(f"Total rows: {stats['total_rows']:,}; unique users: {stats['unique_users']:,}")
    print("Status counts:", {int(k): int(v) for k, v in stats["status_counts"].sort_index().items()})
    print(f"Status codes not in watching_status.csv: {stats['unknown_codes'] or 'none'}")
    print(f"Rows whose anime_id is not in anime.csv: {stats['missing_anime_rows']:,}")
    print(f"Duplicate (user_id, anime_id) pairs inside chunks: {stats['duplicates_in_chunks']:,} "
          "(pairs split across two chunks are not checked here; the sample is checked below)")
    if stats["unknown_codes"]:
        problems.append(f"unknown status codes {stats['unknown_codes']}")
    if stats["duplicates_in_chunks"]:
        problems.append(f"{stats['duplicates_in_chunks']:,} duplicate pairs inside chunks")

    user_ids, eligible_users = sample_users(stats["labeled_per_user"])
    print(f"\nUsers with >= {MIN_LABELED_ENTRIES} labeled entries: {eligible_users:,}")
    if eligible_users < SAMPLE_SIZE:
        print(f"Fewer than {SAMPLE_SIZE:,} eligible users, so all of them are used.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"user_id": user_ids}).to_csv(USER_IDS_PATH, index=False, lineterminator="\n")
    print(f"Sampled {len(user_ids):,} users (seed {SEED}) -> {USER_IDS_PATH.relative_to(PROJECT_ROOT)}")

    print("\nPass 2: collecting the sampled users' rows...", flush=True)
    sample = second_pass(data_dir / "animelist.csv", user_ids, eligible_ids)
    duplicates = int(sample.duplicated(["user_id", "anime_id"]).sum())
    sample = sample.drop_duplicates(["user_id", "anime_id"], keep="first").reset_index(drop=True)
    print(f"Duplicate (user_id, anime_id) pairs dropped from the sample: {duplicates:,}")
    if duplicates:
        problems.append(f"{duplicates:,} duplicate pairs in the sample")
    sample.to_parquet(SAMPLE_PATH, index=False)
    print(f"Saved {SAMPLE_PATH.relative_to(PROJECT_ROOT)}")

    summary = drop_rate_summary(sample)
    q = summary["user_drop_rate_quantiles"]
    print(f"\nSample: {summary['rows']:,} rows; completed {summary['completed']:,}; dropped {summary['dropped']:,}; "
          f"drop rate {summary['drop_rate']:.1%}")
    print(f"Per-user drop rate: min {q[0]:.1%}, 25% {q[0.25]:.1%}, median {q[0.5]:.1%}, "
          f"75% {q[0.75]:.1%}, max {q[1]:.1%}")
    print(f"Users with no drops: {summary['share_users_no_drops']:.1%}; "
          f"users who dropped everything: {summary['share_users_all_drops']:.1%}")
    e = summary["entries_per_user"]
    print(f"Entries per user: min {e['min']}, median {e['median']:g}, max {e['max']}")
    print(f"Distinct anime in the sample: {summary['distinct_anime']:,}")

    result, reasons = verdict(problems, eligible_users, summary["drop_rate"])
    print(f"\nVERDICT: {result}" + (f" ({'; '.join(reasons)})" if reasons else ""))
    print(f"Runtime: {time.monotonic() - started:.0f} s")


if __name__ == "__main__":
    try:
        main()
    except config.ConfigError as error:
        print(f"\nProbe stopped: {error}", file=sys.stderr)
        sys.exit(1)
