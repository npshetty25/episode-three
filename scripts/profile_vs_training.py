"""Where does Nirav's own profile sit compared with the Model B training users?

Run from the episode-three folder:
    python scripts\\profile_vs_training.py

Reads (no AniList or other web requests):
- data/processed/mal_sample_5k_seed42.parquet   the 5,000 training users (TASK 004)
- episode_three.my_entries and titles in MongoDB (Nirav's synced AniList list)
- optional: anime.csv from MAL_DATA_DIR, only to check how MAL types AniList's TV_SHORT shows

Writes reports/profile_vs_training.md. The report holds aggregates only: no titles.
"""
import sys
from collections import Counter
from pathlib import Path

# Lets "python scripts\profile_vs_training.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from episode_three import config, db

SAMPLE_PATH = PROJECT_ROOT / "data" / "processed" / "mal_sample_5k_seed42.parquet"
REPORT_PATH = PROJECT_ROOT / "reports" / "profile_vs_training.md"
COMPLETED_CODE, DROPPED_CODE = 2, 4  # MAL status codes; REPEATING is mapped to 2 by the sync


# --- Pure helpers (tested in tests/test_profile_vs_training.py) --------------

def labelled_entries(entries, titles_by_id, formats=("TV",), min_episodes=None):
    """Nirav's completed/dropped entries on non-adult titles of the given AniList formats.

    `entries` and `titles_by_id` are plain dicts (as read from MongoDB). With
    `min_episodes`, titles must also have a known episode count of at least that many
    (the training data used >= 2).
    """
    kept = []
    for entry in entries:
        if entry["mal_status_code"] not in (COMPLETED_CODE, DROPPED_CODE):
            continue
        title = titles_by_id.get(entry["title_id"])
        if title is None or title.get("format") not in formats or title.get("is_adult"):
            continue
        if min_episodes is not None and not (title.get("episodes") and title["episodes"] >= min_episodes):
            continue
        kept.append(entry)
    return kept


def drop_rate(entries):
    """Share of entries that are dropped (0.0 if there are none)."""
    if not entries:
        return 0.0
    return sum(1 for e in entries if e["mal_status_code"] == DROPPED_CODE) / len(entries)


def percentile_rank(values, value):
    """Percent of `values` that are <= `value` (a value above everyone is 100)."""
    values = list(values)
    return 100.0 * sum(1 for v in values if v <= value) / len(values)


def training_user_stats(sample):
    """One row per training user: labelled entry count and drop rate."""
    is_dropped = sample["watching_status"] == DROPPED_CODE
    return pd.DataFrame({
        "entries": sample.groupby("user_id").size(),
        "drop_rate": is_dropped.groupby(sample["user_id"]).mean(),
    })


def compare_with_training(group, training):
    """Position of one group of Nirav's entries among the training users."""
    n, rate = len(group), drop_rate(group)
    low, high = int(training["entries"].min()), int(training["entries"].max())
    return {
        "n": n, "dropped": sum(1 for e in group if e["mal_status_code"] == DROPPED_CODE), "rate": rate,
        "count_pct": percentile_rank(training["entries"], n),
        "rate_pct": percentile_rank(training["drop_rate"], rate),
        "users_more_entries": int((training["entries"] > n).sum()),
        "users_higher_rate": int((training["drop_rate"] > rate).sum()),
        "count_in_range": low <= n <= high,
        "rate_in_range": float(training["drop_rate"].min()) <= rate <= float(training["drop_rate"].max()),
    }


def position_description(result, low, high):
    """One plain sentence about the entry count: inside or outside the training range, and where."""
    n = result["n"]
    if n > high:
        return (f"OUTSIDE the training range: {n:,} labelled entries is above the training maximum of {high:,} "
                f"(no training user has this many).")
    if n < low:
        return f"OUTSIDE the training range: {n:,} labelled entries is below the training minimum of {low:,}."
    extreme = ""
    if result["count_pct"] >= 99 or result["count_pct"] <= 1:
        more = result["users_more_entries"]
        extreme = f" at the extreme end; only {more:,} of the training users {'has' if more == 1 else 'have'} more,"
    return (f"Inside the training range ({low:,} to {high:,}),{extreme} "
            f"at percentile {result['count_pct']:.2f}.")


# --- TV_SHORT: how does MAL type these shows? ------------------------------

def tv_short_groups(tv_short_entries, titles_by_id):
    """Split TV_SHORT entries by how MAL (Kaggle anime.csv) types them. Returns (groups, note)."""
    try:
        anime = pd.read_csv(config.get_mal_data_dir() / "anime.csv", usecols=["MAL_ID", "Type"],
                            na_values=["Unknown"], encoding="utf-8")
    except (config.ConfigError, FileNotFoundError) as error:
        return None, f"not checked ({error})"
    mal_type = dict(zip(anime["MAL_ID"], anime["Type"]))
    groups = {"typed_tv": [], "typed_other": [], "not_in_2020_snapshot": [], "no_mal_id": []}
    other_types = Counter()
    for entry in tv_short_entries:
        mal_id = titles_by_id[entry["title_id"]].get("mal_id")
        if mal_id is None:
            groups["no_mal_id"].append(entry)
        elif mal_id not in mal_type:
            groups["not_in_2020_snapshot"].append(entry)  # added to MAL after the 2020 snapshot
        elif mal_type[mal_id] == "TV":
            groups["typed_tv"].append(entry)
        else:
            groups["typed_other"].append(entry)
            other_types[str(mal_type[mal_id])] += 1
    groups["other_types"] = dict(other_types)
    return groups, None


# --- Script ----------------------------------------------------------------

def main():
    sys.stdout.reconfigure(errors="backslashreplace")
    if not SAMPLE_PATH.exists():
        print(f"Training sample not found: {SAMPLE_PATH}\nRun scripts\\probe_mal_data.py first.")
        sys.exit(1)

    database = db.get_client()[config.MONGODB_DB]
    username = config.get_anilist_username()
    entries = list(database["my_entries"].find({"source": "anilist", "username": username},
                                               {"title_id": 1, "mal_status_code": 1, "anilist_status": 1}))
    titles = {t["_id"]: t for t in database["titles"].find(
        {"_id": {"$in": list({e["title_id"] for e in entries})}},
        {"format": 1, "is_adult": 1, "episodes": 1, "mal_id": 1})}
    training = training_user_stats(pd.read_parquet(SAMPLE_PATH))
    low, high = int(training["entries"].min()), int(training["entries"].max())

    labelled_all = [e for e in entries if e["mal_status_code"] in (COMPLETED_CODE, DROPPED_CODE)]
    mine = labelled_entries(entries, titles)  # the filter the task specifies: format TV
    mine_strict = labelled_entries(entries, titles, min_episodes=2)
    tv_short = labelled_entries(entries, titles, formats=("TV_SHORT",))
    short_groups, short_note = tv_short_groups(tv_short, titles)

    results = {"main": compare_with_training(mine, training),
               "strict": compare_with_training(mine_strict, training)}
    if short_groups:
        as_mal_low = mine + short_groups["typed_tv"]
        as_mal_high = as_mal_low + short_groups["not_in_2020_snapshot"] + short_groups["no_mal_id"]
        results["mal_low"] = compare_with_training(as_mal_low, training)
        results["mal_high"] = compare_with_training(as_mal_high, training)

    main_result = results["main"]
    count_text = position_description(main_result, low, high)
    rate_low, rate_high = float(training["drop_rate"].min()), float(training["drop_rate"].max())
    rate_text = (f"{'Inside' if main_result['rate_in_range'] else 'OUTSIDE'} the training range "
                 f"({rate_low:.1%} to {rate_high:.1%}), at percentile {main_result['rate_pct']:.1f} "
                 f"(training median {training['drop_rate'].median():.1%}).")

    print(f"Nirav's AniList list: {len(entries):,} entries; {len(labelled_all):,} completed or dropped "
          f"(all formats, adult included; drop rate {drop_rate(labelled_all):.1%})")
    print(f"\nTV format, non-adult, completed vs dropped (the training filter): {main_result['n']:,} entries, "
          f"{main_result['dropped']:,} dropped, drop rate {main_result['rate']:.2%}")
    print(f"  with the training script's extra rule (episodes known and >= 2): {results['strict']['n']:,} entries, "
          f"drop rate {results['strict']['rate']:.2%}")
    print(f"TV_SHORT (non-adult, completed or dropped, excluded above): {len(tv_short):,} entries")
    if short_groups:
        print(f"  MAL types them as TV: {len(short_groups['typed_tv'])}; other: {len(short_groups['typed_other'])} "
              f"{short_groups['other_types']}; added to MAL after 2020 (type unknown here): "
              f"{len(short_groups['not_in_2020_snapshot'])}; no MAL ID: {len(short_groups['no_mal_id'])}")
        for key, label in (("mal_low", "counting TV_SHORT that MAL types as TV"),
                           ("mal_high", "counting every TV_SHORT as TV")):
            r = results[key]
            print(f"  {label}: {r['n']:,} entries, drop rate {r['rate']:.2%} -> "
                  f"{position_description(r, low, high)}")
    else:
        print(f"  MAL type check: {short_note}")
    print(f"\nTraining users ({len(training):,}): entries min {low}, median {training['entries'].median():g}, "
          f"99th pct {training['entries'].quantile(0.99):.0f}, max {high:,}")
    print(f"  Nirav's entry count (TV only): {count_text}")
    print(f"  Nirav's drop rate:             {rate_text}")

    write_report(len(entries), labelled_all, results, training, count_text, rate_text, short_groups, short_note,
                 len(tv_short), low, high)
    print(f"\nWrote {REPORT_PATH.relative_to(PROJECT_ROOT)}")


def write_report(n_entries, labelled_all, results, training, count_text, rate_text, short_groups, short_note,
                 n_tv_short, low, high):
    main_result, strict = results["main"], results["strict"]
    quantiles = training["entries"].quantile([0.5, 0.9, 0.99])
    lines = [
        "# Nirav's profile vs the Model B training users",
        "",
        "- **Generated by:** `python scripts\\profile_vs_training.py` (0 network requests; aggregates only, no "
        "titles). The file has no timestamp on purpose: re-running on unchanged data gives an identical file.",
        f"- **Training users:** {len(training):,} (Kaggle MAL 2020 sample, seed 42; TV, non-adult, "
        "completed vs dropped, at least 20 such entries)",
        f"- **Nirav:** {n_entries:,} entries on AniList; {len(labelled_all):,} completed or dropped across all formats "
        f"(drop rate {drop_rate(labelled_all):.1%})",
        "",
        "## Result",
        "",
        "Nirav's personal features use the **same filter as training**: TV format, non-adult, completed vs dropped "
        "(REPEATING counts as completed).",
        "",
        "| Measure | Nirav | Training users (5,000) | Position |",
        "|---|---|---|---|",
        f"| Labelled entries (TV, non-adult) | **{main_result['n']:,}** | min {low}, "
        f"median {quantiles[0.5]:g}, 90th pct {quantiles[0.9]:.0f}, 99th pct {quantiles[0.99]:.0f}, "
        f"max {high:,} | percentile {main_result['count_pct']:.2f}; "
        f"{main_result['users_more_entries']:,} training user(s) with more |",
        f"| Dropped | {main_result['dropped']:,} | n/a | n/a |",
        f"| Drop rate | **{main_result['rate']:.2%}** | median {training['drop_rate'].median():.1%}, "
        f"mean {training['drop_rate'].mean():.1%}, max {training['drop_rate'].max():.1%} | "
        f"percentile {main_result['rate_pct']:.1f}; {main_result['users_higher_rate']:,} training users higher |",
        "",
        f"- **Entry count:** {count_text}",
        f"- **Drop rate:** {rate_text}",
        "",
        "Same comparison with the training script's extra rule (episode count known and at least 2): "
        f"{strict['n']:,} entries, drop rate {strict['rate']:.2%} "
        f"(percentiles {strict['count_pct']:.2f} and {strict['rate_pct']:.1f}).",
        "",
        "## TV_SHORT: the comparison depends on how MAL types these shows",
        "",
        f"AniList marks {n_tv_short:,} of Nirav's completed/dropped non-adult entries as `TV_SHORT` (episodes of "
        "15 minutes or less). The task's filter (`format == TV`) excludes them. MAL has no such type, and the "
        "training data holds MAL type `TV`.",
        "",
    ]
    if short_groups:
        low_r, high_r = results["mal_low"], results["mal_high"]
        lines += [
            "Using the Kaggle `anime.csv` (MAL's own types, 2020 snapshot) for the shows that exist there:",
            "",
            "| TV_SHORT entries | Count |",
            "|---|---|",
            f"| Typed `TV` by MAL | {len(short_groups['typed_tv'])} |",
            f"| Typed otherwise by MAL {short_groups['other_types']} | {len(short_groups['typed_other'])} |",
            f"| Added to MAL after the 2020 snapshot (type unknown here) | {len(short_groups['not_in_2020_snapshot'])} |",
            f"| No MAL ID | {len(short_groups['no_mal_id'])} |",
            "",
            "So **almost all of the checkable TV_SHORT shows are `TV` on MAL**, and the training data would have "
            "counted them. Sensitivity:",
            "",
            "| Counting | Labelled entries | Drop rate | Entry-count position |",
            "|---|---|---|---|",
            f"| `format == TV` only (task filter) | {main_result['n']:,} | {main_result['rate']:.2%} | "
            f"percentile {main_result['count_pct']:.2f}, {'inside' if main_result['count_in_range'] else 'outside'} |",
            f"| + TV_SHORT that MAL types as TV | {low_r['n']:,} | {low_r['rate']:.2%} | "
            f"percentile {low_r['count_pct']:.2f}, {'inside' if low_r['count_in_range'] else 'OUTSIDE (above the training maximum)'} |",
            f"| + every TV_SHORT | {high_r['n']:,} | {high_r['rate']:.2%} | "
            f"percentile {high_r['count_pct']:.2f}, {'inside' if high_r['count_in_range'] else 'OUTSIDE (above the training maximum)'} |",
            "",
        ]
    else:
        lines += [f"The MAL type check was skipped ({short_note}).", ""]

    lines += [
        "## Caveats to disclose in the Model Report",
        "",
        "1. **His list is a bulk import.** The 12,735 entries were created in one minute from a MyAnimeList export. "
        "Statuses are roughly correct, but they are not a record of choices made on AniList, and progress and dates "
        "are mostly unset (these are never used as features).",
        "2. **Format comparability.** The result above depends on how `TV_SHORT` is counted (see the sensitivity "
        "table). Counted the way MAL types them, his entry count is above everything the model saw in training.",
        f"3. **Only a few drops.** With {main_result['dropped']:,} drops (TV only), his personal drop rate is a "
        "noisy estimate, so predictions for him lean mostly on show-level features.",
        "4. **Extreme volume.** His entry count sits at, or just beyond, the very top of the training range, where "
        "the model has seen almost no similar users. The Model Report must say this next to any prediction shown "
        "for him.",
        "",
        "## Conclusion",
        "",
    ]
    if short_groups and not results["mal_low"]["count_in_range"]:
        lines.append(
            "With the task's filter he is **inside** the training range, at its extreme top for entry count and "
            "typical for drop rate. Counted the way MAL types shows (including TV_SHORT), his entry count is "
            f"**above the training maximum** ({results['mal_low']['n']:,} to {results['mal_high']['n']:,} against "
            f"{high:,}), so the safe statement is that **his profile is at or beyond the edge of the training "
            "range for volume**. His drop rate is typical either way. His profile is usable as a demo with the "
            "disclosures above, and it is not evidence of model accuracy, which comes only from held-out test users.")
    else:
        lines.append(
            "He is inside the training range on both measures, at the extreme top for entry count and typical for "
            "drop rate. His profile is usable as a demo with the disclosures above, and it is not evidence of model "
            "accuracy, which comes only from held-out test users.")
    lines.append("")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except config.ConfigError as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("\nStopped: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
