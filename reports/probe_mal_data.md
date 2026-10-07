# Model B data probe: Kaggle MAL 2020 (TASK 004)

- **Date:** 2026-10-08
- **Script:** `python scripts\probe_mal_data.py`. Runtime 132–137 s (two streaming passes over 109 M rows).
- **Verdict (mechanical): PARTIAL**, because of 540 rows with undocumented status codes and 1 duplicate pair. **Neither reaches the sample.** With the proposed fix (drop rows whose code is not in `watching_status.csv`), every GO criterion is met.
- **Biggest finding:** the dataset stops at late 2020 (max MAL_ID 48,492). **Anime from 2023 onward are not in it at all**, so Model B's anime features for Nirav's current planning list must come from AniList, not from `anime.csv` (see the coverage section).

## Key numbers

| Measure | Value |
|---|---|
| `animelist.csv` rows | **109,224,747** |
| Unique users | **325,770** |
| Anime in `anime.csv` | 17,562 (TV: 4,996) |
| Eligible anime (TV, not Hentai, not Rx, ≥ 2 episodes) | **4,734** |
| Rows whose anime is missing from `anime.csv` | 0 |
| **Eligible users** (≥ 20 completed-or-dropped entries on eligible anime) | **279,458** |
| Sampled users (seed 42) | 5,000 |
| **Sample rows** | **850,801** (completed 784,126; dropped 66,675) |
| **Drop rate** | **7.8%** |
| Entries per user | min 20, median 118, mean 170, max 4,434 |
| Distinct anime in the sample | 4,593 |
| Duplicate pairs in the sample | 0 |
| `sample_user_ids_seed42.csv` SHA-256 | `56d37ec1…3fc3918f`, identical on two runs |

**Per-user drop rate:** min 0%, 25% 0.5%, median 4.1%, 75% 10.7%, max 70.7%. **23.6% of users never drop; none drop everything.** The classes are imbalanced (about 1 drop in 13), so PR-AUC is the right companion metric to ROC-AUC, as planned.

## Status codes

`watching_status.csv` matches the verified table exactly. Its header is `status, description`, with a leading space that the script strips.

| Code | Meaning | Rows in `animelist.csv` |
|---|---|---|
| 1 | Currently Watching | 5,228,658 |
| 2 | **Completed** (label 0) | 68,089,751 |
| 3 | On Hold | 3,700,514 |
| 4 | **Dropped** (label 1) | 4,266,591 |
| 6 | Plan to Watch | 27,938,693 |
| 0 | *not in the table* | 531 |
| 5 | *not in the table* | 6 |
| 33 | *not in the table* | 2 |
| 55 | *not in the table* | 1 |

The 540 rows with undocumented codes are 0.0005% of the data. The `{2, 4}` filter excludes them, so they never reach the sample.

## Verified facts vs the files

| Check | Result |
|---|---|
| `animelist.csv` header | ✅ `user_id, anime_id, rating, watching_status, watched_episodes`; first rows `0,67,9,1,1 / 0,6702,7,1,4 / 0,242,10,1,4` |
| `anime.csv` header (35 columns, through `Score-1`) | ✅ matches |
| `anime.csv` encoding | ✅ **valid UTF-8.** Strict decode succeeded, 162,378 Japanese characters, 0 mojibake sequences. The garbled text Nirav saw was the console, not the file. |
| `Unknown` as missing value | ✅ read with `na_values=["Unknown"]` |
| Status codes | ✅ table matches; ⚠ 540 rows use undocumented codes (above) |
| Other files | `anime_with_synopsis.csv` has 5 columns; its synopsis column is spelled **`sypnopsis`**. `rating_complete.csv` has `user_id, anime_id, rating`. |

## The adult filter (exact strings)

- `Rating` values: `PG-13 - Teens 13 or older` 6,132; `G - All Ages` 5,782; `PG - Children` 1,461; **`Rx - Hentai` 1,345**; `R - 17+ (violence & profanity)` 1,157; `R+ - Mild Nudity` 997; missing 688.
- **The `Hentai` genre token** is in 1,348 rows. Hentai and Rx together: 1,345. Hentai without Rx: 3. Rx without Hentai: 0.
- **Among TV anime: 0 Hentai and 0 Rx.** The adult filter removes nothing from Model B's TV-only pool, so the AND-vs-OR wording difference in TASK 004 (see questions) has no effect on the data.
- TV anime excluded for episodes: 262 with unknown episode counts (typically long-running or then-airing shows); 0 with a single episode.

## Duplicates

- Inside chunks: **1** duplicate `(user_id, anime_id)` pair in the full file.
- Across chunks: not checked in pass 1. The file is ordered by user, so only a user split across a chunk boundary could hide one.
- **In the final sample: 0 duplicates**, checked after collecting all of a sampled user's rows.

## Why Parquet (pyarrow)

The sample is 850,801 rows. Parquet keeps the small integer types (`int32` / `int8`), compresses the file to **2.6 MB**, and loads in well under a second. A CSV would lose the types and be several times larger. pandas needs `pyarrow` to write Parquet. All new libraries support Python 3.13: pandas 3.0.6, numpy 2.5.3, pyarrow 25.0.1, pytest 9.1.1.

## Leakage: what Phase 7 must not do

- **Same-row columns describe the outcome.** In the sample, dropped rows have a median of **2 episodes watched**, against **13** for completed rows. Their mean rating is **4.8 vs 7.6**, and **51% vs 13%** are unrated (`rating == 0`). Using `watched_episodes` or `rating` of the row being predicted would hand the model the answer.
- **`anime.csv`'s `Completed` / `Dropped` / `Watching` counts are a leak.** They are computed from **all** MAL users, including the validation and test users, so a test user's own drop is baked into the feature.
- **How to compute drop rates properly in Phase 7:**
  1. Split users first (`GroupShuffleSplit`).
  2. Compute each anime's drop rate from **training users' history entries only**, smoothed toward the global rate: `(drops + k × global_rate) / (entries + k)`, with k around 10, so rarely-watched anime don't get extreme values.
  3. Apply those training-derived numbers unchanged to validation and test users.
  4. Anime never seen in training get the global rate.

## AniList → MAL mapping, and a coverage gap

- **The mapping works.** One live request (`Page.media(id_in: …) { idMal }`) for 10 recent shows (Fall 2025–Spring 2026) returned **10/10 with an `idMal`**. All 72 shows from the TASK 003 probe also have one (from cached listings, 0 extra requests).
- **But recent shows are not in the 2020 dataset.** The highest MAL_ID in `anime.csv` is **48,492**, and **0 of the 10 recent shows** are in it. TASK 003 sample shows present in `anime.csv`, by year: 2016–2020 6/6 each; 2021 3/6; 2022 2/6; **2023, 2024, 2025: 0/6 each**; 2026 1/12.
- **Consequence for inference:** for shows Nirav is planning now, `mal_anime` has no row. Model B's anime features (episodes, source, genres, community score, members, drop rate) must come from AniList, or be features that exist for both datasets. See question 3.

## Verdict

**PARTIAL**, from the pre-written rules:

| Rule | Result |
|---|---|
| Files readable | ✅ |
| Status table matches | ✅, but the data has unexpected codes (0, 5, 33, 55; 540 rows) |
| Duplicates | ⚠ 1 duplicate pair in the full file (0 in the sample) |
| ≥ 5,000 eligible users | ✅ 279,458 |
| Drop rate 5–40% | ✅ 7.8% |

**Proposed fix:** treat any code not in `watching_status.csv` as invalid. Drop those rows in Phase 7's importer and log the count. The duplicate is resolved by `drop_duplicates` on `(user_id, anime_id)`, which the sample step already does. Neither problem changes the sample, so **Model B can proceed on this data.**

## Questions for the instructor

1. **Verdict:** accept PARTIAL with the fix above (drop undocumented codes and log them), and treat Model B's data as cleared?
2. **Adult filter wording:** the TASK 004 context says Hentai **AND** Rx; requirement 5 says not Hentai, not Rx (**OR**). I implemented OR, the stricter one. The difference is 3 anime, none of them TV, so the data is unaffected. Which wording goes in the spec?
3. **Coverage gap: anime features at inference.** Recent shows have no `anime.csv` row. The options I see:
   - **(a)** Use only features that both sources provide (episodes, format, source, genres, community score, popularity/members), and take them from AniList at inference. This needs scale mapping (score 0–100 vs 1–10; AniList popularity vs MAL members).
   - **(b)** Fetch AniList data for the ~4,600 training anime via `idMal_in` (~95 requests). Training and inference would then use the same AniList features, which removes the train/serve mismatch.
   - **(c)** For the drop-rate feature: training-derived rates exist only for 2020-era anime. New shows would get a genre-level prior, or AniList's `stats.statusDistribution` (DROPPED/COMPLETED counts), which exists for new shows. The latter is a different population, so it needs care.

   I lean towards **(b) + (c with AniList status counts)**, so the model sees the same kind of features in training and at inference.
4. **Storage:** the real sample averages **170 entries per user**, not 200. That puts `mal_user_lists` at about 850,801 × 95 B ≈ **81 MB** (spec estimate: 95 MB).
5. **Excluded:** 262 TV anime with unknown episode counts (long-runners or then-airing shows). Is that acceptable for v1?

## Reproduce

```
python scripts\probe_mal_data.py
Get-FileHash data\processed\sample_user_ids_seed42.csv
```
