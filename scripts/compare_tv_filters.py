"""Compare the "MAL TV" and "AniList TV" definitions on the Kaggle sample and on Nirav's list. 0 AniList requests.

Run from the episode-three folder (after collect_model_b_anime):
    python -m scripts.compare_tv_filters                     # includes one pass over the full animelist.csv (1-3 min)
    python -m scripts.compare_tv_filters --skip-full-scan    # skip that pass

Reads: anime.csv and animelist.csv from MAL_DATA_DIR (local), the sample parquet, and model_b_anime / titles /
my_entries from Atlas. Nothing is written and nothing is fetched.
"""
import argparse
import sys
import time
from pathlib import Path

# Lets "python scripts\compare_tv_filters.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from episode_three import anilist_sync, config, db
from episode_three.collect import model_b_anime as mba
from episode_three.features import tv_filters as tf
from scripts.profile_vs_training import drop_rate, labelled_entries

SAMPLE_PATH = PROJECT_ROOT / "data" / "processed" / "mal_sample_5k_seed42.parquet"


def n(value):
    return f"{value:,}"


def pct(part, whole):
    return f"{100 * part / whole:.1f}%" if whole else "-"


def section_sample(sample, formats, mal_type):
    print("\n=== 1. The Kaggle sample under three TV definitions ===")
    result = tf.filter_scenarios(sample, formats, mal_type)
    print(f"  {'definition':<26}{'rows':>10}{'anime':>8}{'users kept (>=20)':>20}{'users below 20':>16}{'drop rate':>11}")
    labels = {"i_mal_tv": "(i) MAL Type = TV (now)", "ii_anilist_tv": "(ii) AniList format = TV", "iii_both": "(iii) both"}
    for key, row in result.items():
        print(f"  {labels[key]:<26}{n(row['rows']):>10}{n(row['anime']):>8}{n(row['users_kept']):>20}"
              f"{n(row['users_below_min']):>16}{100 * row['drop_rate']:>10.2f}%")
    split = tf.mal_tv_by_anilist_format(sample, formats)
    total_anime, total_rows = sum(split["anime"].values()), sum(split["rows"].values())
    print(f"\n  MAL-TV anime in the sample by their AniList format ({n(total_anime)} anime, {n(total_rows)} rows):")
    for fmt in split["anime"]:
        print(f"    {fmt:<22}{n(split['anime'][fmt]):>6} anime ({pct(split['anime'][fmt], total_anime):>6})   "
              f"{n(split['rows'][fmt]):>8} rows ({pct(split['rows'][fmt], total_rows):>6})")
    non_tv = total_anime - split["anime"].get("TV", 0)
    print(f"  => {n(non_tv)} MAL-TV anime ({pct(non_tv, total_anime)}) are not AniList TV, "
          f"{n(total_rows - split['rows'].get('TV', 0))} rows ({pct(total_rows - split['rows'].get('TV', 0), total_rows)}).")


def section_coverage(sample, docs, anime_csv):
    print("\n=== 4. Coverage ===")
    c = tf.coverage(sample, docs)
    print(f"  sample rows whose anime has an AniList record: {n(c['rows_with_record'])} of {n(c['rows'])} ({pct(c['rows_with_record'], c['rows'])})")
    print(f"  sample rows with a usable drop_share (completed + dropped > 0): {n(c['rows_with_drop_share'])} ({pct(c['rows_with_drop_share'], c['rows'])})")
    print(f"  sample anime with a record: {n(c['anime_with_record'])} of {n(c['anime'])}; with a usable drop_share: {n(c['anime_with_drop_share'])}")
    u = tf.unknown_episode_tv(anime_csv, docs)
    print(f"  MAL TV anime with unknown episodes in anime.csv: {n(u['mal_tv_unknown_episodes'])}; fetched from AniList: {n(u['fetched'])}, "
          f"of which AniList now has an episode count: {n(u['with_episodes_on_anilist'])}")
    if u["not_fetched"]:
        print(f"    {n(u['not_fetched'])} of them are NOT in the universe (the sample required known episodes), so their AniList "
              f"episodes are unknown; fetching them would cost {-(-u['not_fetched'] // 50)} requests.")


def section_nirav(entries, titles, mal_type):
    print("\n=== 2. Nirav under AniList TV ===")
    out = tf.nirav_comparison(entries, titles, mal_type, labelled_entries, drop_rate)
    print(f"  labelled (completed + dropped, non-adult, AniList TV): {n(out['labelled'])}, dropped {n(out['dropped'])} ({100 * out['drop_rate']:.1f}%)")
    print(f"  of those, MAL type is not TV: {n(out['mal_non_tv'])} " + (str(out["mal_non_tv_types"]) if out["mal_non_tv"] else "")
          + f"; not in the 2020 anime.csv (added to MAL later, type unknown): {n(out['not_in_2020_csv'])}")
    return out


def section_opposite(nirav, mal_type, anime_csv, docs, skip_scan):
    print("\n=== 3. The opposite direction: AniList TV but MAL non-TV ===")
    print("  The sample was filtered on MAL TV, so these anime cannot be in it. AniList formats are only known for the anime we fetched")
    print("  (the sample's anime + Nirav's), so the only AniList-TV / MAL-non-TV anime we can identify are Nirav's:")
    ids = nirav["non_tv_mal_ids"]
    print(f"  Nirav's AniList-TV anime that MAL types as non-TV: {n(len(ids))}")
    if ids and not skip_scan:
        began = time.monotonic()
        out = tf.count_rows_for_ids(config.get_mal_data_dir() / "animelist.csv", ids)
        print(f"  In the FULL animelist.csv ({n(out['file_rows'])} rows, read in chunks, {time.monotonic() - began:.0f} s): "
              f"{n(out['rows'])} completed/dropped rows from {n(out['users'])} users on {n(out['anime_with_rows'])} of those anime.")
        print(f"  (the current sample has 850,801 rows from 5,000 users; the full data has far more users, so this is the pool a widened filter could add)")
    elif ids:
        print("  (full-file scan skipped)")
    mal_non_tv = anime_csv[anime_csv["Type"] != "TV"]
    print(f"  anime.csv has {n(len(anime_csv))} anime, {n(len(mal_non_tv))} not MAL TV: " + ", ".join(
        f"{t} {n(c)}" for t, c in mal_non_tv["Type"].fillna("unknown").value_counts().items()))
    missing, requests = tf.extra_mapping_requests(anime_csv["MAL_ID"].astype(int), (d["mal_id"] for d in docs.values() if d.get("mal_id")))
    print(f"  To learn the AniList format of EVERY anime in anime.csv we would still need {n(missing)} lookups = {requests} more requests "
          f"(about {requests * 2.2 / 60:.0f} min at 27/min); only then could the sample be redrawn with an AniList-TV filter, locally.")


def main():
    parser = argparse.ArgumentParser(description="Compare MAL TV and AniList TV (0 requests).")
    parser.add_argument("--skip-full-scan", action="store_true", help="skip the pass over the full animelist.csv")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")

    database = db.get_client()[config.MONGODB_DB]
    print(f"Database: {database.name}")
    anilist_sync.ping_database(database)
    sample = pd.read_parquet(SAMPLE_PATH)
    anime_csv = pd.read_csv(config.get_mal_data_dir() / "anime.csv", na_values=["Unknown"], encoding="utf-8",
                            usecols=["MAL_ID", "Type", "Episodes"])
    mal_type = dict(zip(anime_csv["MAL_ID"].astype(int), anime_csv["Type"]))   # a blank Type stays NaN (treated as unknown)
    docs = {d["mal_id"]: d for d in database[mba.COLLECTION].find({}) if d.get("mal_id") is not None}
    formats = {mal_id: d["format"] for mal_id, d in docs.items()}
    unmapped = database[mba.UNMAPPED].count_documents({})
    sample_ids = set(sample["anime_id"].unique())
    pending = len(sample_ids - set(docs) - {d["mal_id"] for d in database[mba.UNMAPPED].find({}, {"mal_id": 1})})
    print(f"Sample: {n(len(sample))} rows, {n(sample['user_id'].nunique())} users, {n(len(sample_ids))} anime. "
          f"model_b_anime: {n(len(docs))} documents; unmapped MAL ids: {n(unmapped)}.")
    if pending:
        print(f"WARNING: {n(pending)} sample anime are neither stored nor known unmapped: run collect_model_b_anime first, "
              "the numbers below are incomplete.")

    titles = {t["_id"]: t for t in database["titles"].find({})}
    entries = list(database["my_entries"].find({"source": "anilist"}))
    section_sample(sample, formats, mal_type)
    nirav = section_nirav(entries, titles, mal_type)
    section_opposite(nirav, mal_type, anime_csv, docs, args.skip_full_scan)
    section_coverage(sample, docs, anime_csv)
    print("\n(0 AniList requests used. Nothing was written.)")


if __name__ == "__main__":
    try:
        main()
    except config.ConfigError as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nStopped: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
