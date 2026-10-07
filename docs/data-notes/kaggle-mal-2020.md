# Data notes: Kaggle "Anime Recommendation Database 2020"

Used for Model B (finish vs drop) training data. Decided in spec v1.2 (§4.6, OPEN-1).

## Source and license

- **Kaggle:** https://www.kaggle.com/datasets/hernan4444/anime-recommendation-database-2020
- **GitHub mirror (scraper and notes):** https://github.com/Hernan4444/MyAnimeList-Database
- **License shown on Kaggle:** CC0: Public Domain. Version 7, "Updated 5 years ago", update frequency "Never" (checked by Nirav, 2026-10).
- **Provenance caveat:** the data was scraped from MyAnimeList through the Jikan API. MyAnimeList's own terms restrict aggregating their data, and the CC0 label is the uploader's claim, not MAL's. So:
  - non-commercial, educational use only;
  - **never commit raw data or user-level rows** (the files live outside the repo in `MAL_DATA_DIR`; derived samples go to `data/processed/`, which is git-ignored);
  - the README must say the project is **not affiliated with MyAnimeList**, and state the limitation **"2020 snapshot; shows after 2020 are not in the data"**.

## Files

| File | Size | What it is |
|---|---|---|
| `animelist.csv` | 1,937 MB | Every user's list: one row per (user, anime) |
| `anime.csv` | 5.4 MB | One row per anime: metadata and community counts |
| `anime_with_synopsis.csv` | 6.9 MB | MAL_ID, name, score, genres, synopsis |
| `rating_complete.csv` | 780 MB | Ratings of completed anime only (not used by Model B) |
| `watching_status.csv` | 88 bytes | Status code table |

## Verified headers

- `animelist.csv`: `user_id,anime_id,rating,watching_status,watched_episodes`. The score column is called `rating` (0 = not rated). User IDs are numeric and start at 0.
- `anime.csv`: `MAL_ID, Name, Score, Genres, English name, Japanese name, Type, Episodes, Aired, Premiered, Producers, Licensors, Studios, Source, Duration, Rating, Ranked, Popularity, Members, Favorites, Watching, Completed, On-Hold, Dropped, Plan to Watch, Score-10 … Score-1`.
  - Missing values are the string `Unknown`, so read with `na_values=["Unknown"]` and `encoding="utf-8"`.
  - `Rating` here is the **age rating** (e.g. `R - 17+ (violence & profanity)`), not a score.

## Watching status codes

| Code | Meaning | Used by Model B |
|---|---|---|
| 1 | Currently Watching | no |
| 2 | Completed | yes (label 0) |
| 3 | On Hold | no |
| 4 | Dropped | yes (label 1) |
| 6 | Plan to Watch | no |

There is no code 5. `scripts/probe_mal_data.py` reads this file at runtime and flags any difference.

## Eligibility used by Model B (TASK 004)

- **Anime:** `Type == "TV"`, `Genres` does not contain `Hentai`, `Rating` does not start with `Rx`, and `Episodes` known and ≥ 2.
- **Rows:** eligible anime with status 2 (Completed) or 4 (Dropped).
- **Users:** at least 20 such rows. The sample is 5,000 users drawn with `numpy.random.default_rng(42)` from the sorted eligible user IDs.

## Leakage notes

- `rating` and `watched_episodes` on the **same row** describe the outcome (people who drop a show have watched fewer episodes and often rate it lower). They must never be features for that row.
- `anime.csv`'s `Completed` / `Dropped` / `Watching` counts are computed from **all** users, including the ones we test on. Per-anime drop rates must be recomputed from **training users only** (Phase 7).
