# Episode Three: Project Spec v1.4 (2026-10-10)

> Written by the instructor; saved here verbatim by TASK 002. Changes to the plan go into a new spec version with a changelog entry, not silent edits.

## Changelog

**v1.4 (2026-10-10)**, the instructor's rulings after the TASK 006 terms check:
1. **TMDB rejected.** Its API terms (https://www.themoviedb.org/api-terms-of-use) prohibit use *"in connection with, including for training, a machine learning (ML) or artificial intelligence (AI) based Application"*; Episode Three is an ML application (§4.3).
2. **Phase 11's TMDB-based TV Model A is dropped** (§2, §11, §16).
3. **Trakt rejected** for Phase 4: free accounts are limited to 250 watchlist items and (since July 2026) one connected community app, the limits keep changing, and OAuth with refresh tokens adds work (§4.2). The TV/movie approach follows in a revised TASK 006: **TV via TVMaze, movies as minimal manual entries**; our database is their source of truth, so backups are needed from Phase 4.
4. **`--stale` rule deviation (TASK 005):** an imported entry is listed only while `updated_at ≤ created_at + IMPORT_EDIT_GRACE_SECONDS` (60), i.e. until it is edited on AniList. **The 180-day rule still applies** to every CURRENT/PAUSED entry, imported or not (confirmed in code and by a test) (§5).
6. **Full MAL history re-imported (2026-10-10):** Nirav replaced his 139-entry list with his full history, **12,735 entries** (COMPLETED 12,017, PLANNING 338, DROPPED 203, PAUSED 103, CURRENT 74), all created at 12:59 UTC. `MAL_IMPORT_CUTOFF` moved to 2026-10-10 14:00 UTC, so all are `origin: "mal_import"`. A sync is now **26 requests** (500 entries per chunk, ~1 min); `episode_three` is 15.2 MB (§5, §6).
5. **AniList sync safety (TASK 006 Part C):** AniList entry documents carry `source: "anilist"`; the sync reads and deletes **only** documents matching `source = "anilist"` AND `username`, so manual TV/movie entries in `my_entries` can never be deleted by it. `synced_at` is renamed `content_changed_at` (last time the content actually changed) on AniList entries and titles (§5).

**v1.3 (2026-10-08)**, the instructor's rulings after TASK 004, plus the tracker decision:
1. Model B data **CLEARED**. TASK 004's PARTIAL is accepted: the Phase 7 importer drops and logs undocumented status codes (0/5/33/55) and duplicate pairs (§4.6).
2. Adult filter = **OR**: exclude if `Genres` contains "Hentai" OR `Rating` starts with "Rx" (§4.6).
3. Model B **show-level features come from AniList** for both training and inference anime (fetch ~4,600 training anime via `idMal_in`, ~95 requests, minimal fields). The drop-share feature uses AniList `stats.statusDistribution` for both. The training-user smoothed drop rate is a Phase 8 experiment. Flag: the drop share of currently airing shows is immature (§7).
4. Known coverage gap: the Kaggle data has no anime after ~2020 (0/10 recent shows present); this is why ruling 3 exists. README limitation (§4.6).
5. Storage estimate for `mal_user_lists` ≈ 81 MB (mean 170 entries/user) (§5).
6. 262 TV anime with unknown episode counts are excluded for v1; note it in the Phase 8 report (§4.6).
7. **Tracker decision:** AniList is Nirav's tracker. Our own anime tracker in MongoDB is NOT allowed (AniList terms, clause 5). MAL was considered and rejected. TV/movies: decided in Phase 4 (§4.1, §5).
8. Status mapping AniList → MAL training codes (§5).
9. Entry `origin` = "mal_import" or "anilist", from the real `createdAt` data. Imported entries have stale progress and mostly unset dates; Model B never uses progress or dates (§5).

**v1.2 (2026-10-07)**, the instructor's rulings after the TASK 003 probe:
1. Model A season window: **Fall 2018 → Summer 2026**. Earlier seasons are excluded (no usable daily trend records) (§6).
2. New eligibility filter: exclude shows whose episode duration is < 10 min (§6).
3. Trend dates are **JST days**; "has score" means `averageScore > 0` (§4.1, §7).
4. Marker day M(n) defined (§7).
5. ep3 and ep1 snapshot definitions, with the `multi_episode_premiere` flag (§7).
6. **Primary finale label = the last releasing record** (finale-day record), stored with `label_source`. Finale +7 days is a secondary sensitivity label reported in Phase 6 (§7).
7. Collection method = **option C**: `mediaId_in` batches of ~10, date windows only; every query names only the filters it uses (§4.1, §6).
8. Risk 4 rewritten: `X-RateLimit-Remaining` does not predict 429s; `Retry-After` is the real protection (§4.1, §16).
9. Open item for Phase 5: test `airingSchedules` with `mediaId_in` (§16).
10. Open item: confirm Summer 2026 shows have reached finale + 7 days before counting them (§16).
11. Model B data decided: the hernan4444 Kaggle dataset for v1, with an optional later time-based test on the svanoo 2022 dataset (§4.6, OPEN-1).

Also updated: §9 pandas, numpy, pyarrow and pytest installed in TASK 004.

**v1.1 (2026-10-04)**, after TASK 002:
1. `mal_user_lists._id` is a prefixed string, `"mal_user:<id>"`. No exceptions to the `_id` convention (§5).
2. Storage estimate revised: an embedded user-list entry is about 95 B in BSON, so `mal_user_lists` ≈ 95 MB and the project ≈ 145 MB. Measure with `dbStats` right after the import (§5).
3. Constraints: no weekly-hour cap and no deadline; phases are sized for quality, not speed (§14).
4. Model A snapshot definitions (ep1, ep3, finale) are **PENDING TASK 003**, because `MediaTrend.episode` is the episode released on that day (§7).
5. New standing engineering rules: batch writes, timeouts on every network call, resumable long jobs (§5).
6. Workflow: small commits, one per logical change (§10).

Also updated: §9 `requests` installed in TASK 003 (needed for the probe); §5 sample dataset dropped in TASK 002.

**v1.0 (2026-10-04):** first version.

## 1. Goal and positioning

**The problem.** Trackers record what you've watched, but they can't answer two questions every viewer has: "Is this new show worth continuing?" and "Will I actually finish this?"

**One-sentence pitch.** A personal tracker for everything I watch and listen to, with two ML models: one predicts a new anime season's final score after only three episodes, the other predicts whether I personally will finish or drop a show.

**What is NOT unique (say this openly in the README):**
- Unified tracking of anime, shows, and movies: Ryot and Simkl already do this.
- Linking anime to their opening/ending songs: the Kitsune app does this, and the AniMusic student project generates playlists from AniList watch history.

**What IS unique (as far as our research found):**
- Model A: predicting a season's *final* score from data available after episode 3.
- Model B: a per-user finish-vs-drop predictor.
- The two combined: Model A's prediction feeds Model B for currently airing shows.

**Claims Nirav must never make:**
- "Nothing like this exists" or "the first tracker that..."
- "Predicts whether you'll like a show" (Model B predicts finishing vs dropping, not enjoyment).
- Any accuracy number not produced by our own test-set evaluation.
- That the models use real-time data if they use snapshots.
- Anything implying endorsement by AniList, TMDB, Trakt, or YouTube.

## 2. Scope

**MVP features:**
1. Anime tracker synced from Nirav's AniList account.
2. TV and movie tracker. *(v1.4: our own tracker, not Trakt; TV metadata via TVMaze, movies as minimal manual entries; details in the revised TASK 006.)*
3. Model A (anime only), trained and evaluated against baselines.
4. Model B (anime only), trained and evaluated against baselines.
5. Streamlit dashboard: Home, Tracker, Season Forecast, Will I Finish?, Model Report, About & Credits.

**Later features (after MVP):**
- YouTube Music: listening history, playlist sync, anime theme-song links, "you replay this opening but haven't watched the show."
- ~~TMDB enrichment (posters, episode ratings) and an experimental Model A for TV shows.~~ **Dropped in v1.4** (TMDB's terms prohibit use with ML/AI applications).
- Synced lyrics for the current song.

**Out of scope:** Java/JavaFX, desktop widget, FastAPI service, Spotify, public deployment, multi-user accounts, survival analysis, writing data back to AniList or Trakt.

**MVP definition of done:**
- Both syncs run repeatedly without creating duplicates.
- Both models have a committed evaluation report showing results against every baseline.
- All MVP dashboard pages work locally.
- Tests pass.
- The README draft includes the results table and an honest limitations section.

## 3. Features (what Nirav sees)

| Feature | On screen | What it does |
|---|---|---|
| Anime sync | "Last synced" time on Home | Pulls Nirav's AniList list and upserts it into MongoDB |
| TV/movie tracker | Same | *v1.4: hand-entered entries (TV via TVMaze, movies minimal); not Trakt* |
| Tracker | Table with filters (type, status, year) and cover images | Shows all entries in one place |
| Season Forecast | Current-season anime with at least 3 aired episodes: episode-3 score, predicted finale score ± typical error | Model A |
| Will I Finish? | Nirav's planning list ranked by drop probability | Model B |
| Model Report | Metrics vs baselines, error charts | Reads committed evaluation reports |
| About & Credits | Data-source credits, limitations (v1.4: no TMDB notice; TMDB not used) | Satisfies attribution terms |
| *(Later)* Music | Recent plays, top artists, playlists, theme-song links | YouTube Music and AnimeThemes |

## 4. Data sources

### 4.1 AniList GraphQL (anime: Nirav's list, metadata, score trends)
- **Endpoint:** `POST https://graphql.anilist.co`, JSON body `{"query": ..., "variables": ...}`. Docs: https://docs.anilist.co
- **Auth:** none for public data. Nirav's list must be public, or we add OAuth later. No account or key needed for MVP.
- **Rate limit:** the API is currently degraded and limited to 30 requests per minute as a temporary measure, normally 90. Exceeding it gives a 1-minute timeout, and a separate burst limiter blocks too many requests in a very short period.
  - **Our rule:** one shared helper sleeps about 2.2 seconds between requests (≈27/min), and on HTTP 429 waits for `Retry-After` seconds before retrying.
  - **v1.2:** responses show `X-RateLimit-Limit: 30`, but 429s also arrive while `X-RateLimit-Remaining` is 20+ (a hidden limiter, TASK 003). `Retry-After` is the real protection; `Remaining` cannot be used to avoid 429s.
- **Query rules (v1.2, from TASK 003):**
  - Every query names only the filters it uses. Filters passed as `null` are not ignored: `mediaId_in: null` → HTTP 500, `episode_lesser: null` / `date_greater: null` → HTTP 400.
  - Paginate with `hasNextPage` only; `pageInfo.total` is a placeholder (always 5000).
  - Trend `date` values are stamped at 00:00 JST: all day arithmetic uses **JST days**. A record "has a score" only if `averageScore > 0` (each show's first releasing day has 0).
- **Key queries and fields:**
  - **Nirav's list:** `MediaListCollection(userName, type: ANIME)` → `lists { entries { status progress score startedAt completedAt updatedAt media { id idMal ... } } }`. Entries come in chunks, max 500 per chunk, so loop chunks.
  - **Season listing:** `Page(perPage: 50) { media(season, seasonYear, type: ANIME, format_in: [TV, ONA]) {...} }`. Page allows max 50 entries per page.
  - **Score trends:** `Page { mediaTrends(mediaId, releasing: true, sort: DATE) { date episode averageScore popularity inProgress trending } }`. Media trends are documented as the media's daily trend stats, with a filter for stats recorded while the media was releasing.
  - **Media fields we keep:** `id idMal title format episodes duration season seasonYear source countryOfOrigin isAdult genres tags{name rank} studios(isMain:true){nodes{name}} averageScore popularity relations{edges{relationType node{id}}} coverImage{medium}`.
- **Terms of use (important):** AniList is free for non-commercial use, prohibits using the API as a backup or data storage service, prohibits hoarding or mass collection of data, and prohibits use within competing services such as list/tracker services, unless they provide significant sustained syncing with AniList. For purely educational projects like school assignments, they say they tend to be lenient on the mass-collection rule.
  - **Design consequences:**
    - AniList stays the source of truth for Nirav's anime. We only *read* and sync it; we never maintain a separate anime list.
    - **Tracker decision (v1.3).** AniList is Nirav's tracker. Clause 5 of https://docs.anilist.co/guide/terms-of-use prohibits using the API within competing, non-complementary services of the same nature (including anime list/tracker services), for user data and media data. So this app is a **dashboard on top of AniList**: it reads only Nirav's own public list (`MediaListCollection`, no OAuth), never writes to it, never offers tracking to others, stores only fields the app uses, and does not fetch `notes`. Building our own anime tracker in MongoDB is **not allowed**. MAL was considered as the tracker and rejected (its API terms are unverified, and it carries the same "competing service" risk). TV/movies are decided in Phase 4 (AniList's rule does not apply there).
    - `MediaListCollection` returns the whole list at once, capped at the 11,000 most recently updated entries. Chunked with `chunk`/`perChunk` (max 500) + `hasNextChunk`. Scores are fetched as `score(format: POINT_100)`.
    - **Unknown username:** HTTP 404, `errors: [{"message": "User not found"}]`, `data.MediaListCollection: null` (TASK 005); the sync turns it into a clear error.
    - Model A collection stays modest (about 1,000 shows).
    - We do not mass-collect other users' lists (see OPEN-1).
    - The app name never contains "AniList".

### 4.2 Trakt (TV and movies: Nirav's history): **REJECTED (v1.4)**
- **Why rejected:** free accounts are limited to 250 watchlist items and, since July 2026, one connected community app; the limits keep changing; OAuth with refresh tokens adds work. The v1.0 notes below are kept for reference only.
- **Base URL:** `https://api.trakt.tv`. Headers: `trakt-api-version: 2`, `trakt-api-key: <client_id>`, `Authorization: Bearer <token>`. Docs: https://trakt.docs.apiary.io
- **Auth:** OAuth 2.0 device flow: request a device code from /oauth/device/code, then poll /oauth/device/token, the flow intended for TV, console, and CLI apps.
- **Accounts to create:** a Trakt account and an API app (gives client ID and secret, stored in `.env`).
- **Endpoints (verify in docs during Phase 4):** `GET /sync/watched/shows`, `GET /sync/watched/movies`, `GET /sync/history`, and `GET /users/hidden/dropped`, which retrieves the user's dropped shows.
- **Rate limit:** a Trakt GitHub issue this week cites 500 unauthenticated GET requests per 5 minutes. Authenticated limits are in the docs. We make only a handful of calls, but still handle HTTP 429.
- **Caveat:** Trakt is changing account limits in 2026. Free accounts get a bigger watchlist of 250 instead of 100. Watch history isn't affected for our scale.

### 4.3 TMDB (later: posters, TV episode ratings): **REJECTED (v1.4)**
- **Why rejected:** TMDB's API terms (https://www.themoviedb.org/api-terms-of-use) prohibit using the TMDB APIs or TMDB Content *"in connection with, including for training, a machine learning (ML) or artificial intelligence (AI) based Application"*. Episode Three is an ML application, so TMDB is not used anywhere: no tracker metadata and no TV model. (TASK 006 terms check; the pages were read via search extracts because Nirav's ISP blocks themoviedb.org at DNS level and the site serves a bot challenge to scripts.)
- The v1.0 notes below are kept for reference only.
- **Base URL:** `https://api.themoviedb.org/3`. Auth: API Read Access Token as a Bearer header. Account and API key application required.
- **Endpoint:** `GET /tv/{series_id}/season/{season_number}`, whose response includes episodes with `vote_average` and `vote_count`.
- **Rate limit:** TMDB disabled its legacy limits in 2019 but still has upper limits somewhere around 40 requests per second, and asks you to respect 429s.
- **Terms:** free for non-commercial use with attribution; you must use the TMDB logo and show the notice that the product uses the TMDB API but is not endorsed or certified by TMDB, inside an About or Credits section. A third-party summary says the terms forbid caching TMDB data for longer than six months; verify in the terms when we reach that phase.

### 4.4 ytmusicapi (later: YouTube Music)
- **Docs:** https://ytmusicapi.readthedocs.io (stable docs are version 1.12.3). Unofficial and can break.
- **Auth:** the docs call OAuth the simplest authentication method, but YouTube removed ytmusicapi's shared OAuth client in November 2024, so you need your own client ID from Google Cloud. The CLI now labels browser-cookie setup as deprecated. **OPEN-7.**
- **Calls:** `get_history()`, `get_library_playlists()`, `get_playlist()`, `get_lyrics()`.
- **Caveat:** history items carry relative labels ("Today", "Yesterday") rather than exact timestamps. Verify in Phase 10. Deduplication will rely on observed order, not timestamps.

### 4.5 AnimeThemes (later: theme songs)
- **Use GraphQL** at `https://graphql.animethemes.moe` (explorer: `/graphiql`). The JSON:API is deprecated and will be removed.
- **Rate limit:** 90 requests per minute; respect `Retry-After`.
- Exact query (anime by AniList ID → themes → songs → artists) to be confirmed in the explorer during Phase 10.

### 4.6 Kaggle MyAnimeList 2020 dataset (Model B training data, recommended)
- https://www.kaggle.com/hernan4444/anime-recommendation-database-2020 (manual download with a Kaggle account).
- `animelist.csv` holds every user's anime with score, watching status, and number of episodes watched: 109 million rows covering 17,562 anime and 325,772 users, about 1.9 GB. Users are numeric IDs, not usernames.
- **Caveat:** it includes adult anime, which we filter out. The license still needs checking on the Kaggle page (Task 004).
- **Decided for v1 (v1.2):** Kaggle shows License = CC0: Public Domain (Version 7, updated ~2021, update frequency "Never"). The data was scraped from MyAnimeList via Jikan, and MAL's terms restrict aggregation, so: non-commercial use only, never commit raw data or user-level rows, and the README states "not affiliated with MyAnimeList" plus the limitation "2020 snapshot; shows after 2020 are absent". Details: `docs/data-notes/kaggle-mal-2020.md`.
- **Optional later:** the svanoo "MyAnimeList Dataset" (2022-03-27 snapshot, has status and `last_interaction_date`, ~14 GB) for a time-based test; a small recent AniList sample only after emailing contact@anilist.co.

### OPEN-1: Model B training data
- **(a) Kaggle MAL 2020 sample.** No API collection, no terms risk, data already anonymized. Downsides: 2020 data, MAL users rather than AniList users.
- **(b) Collect AniList user lists.** Fresh data, but conflicts with the no-mass-collection rule unless AniList agrees.
- **(c) Both:** train on Kaggle, then validate on a small AniList sample (about 300 users) only after emailing contact@anilist.co.
- **Recommendation: (a) for MVP, (c) as an optional extension.** It also gives a good interview answer: "I read the API terms and designed around them."
- **Decided (v1.2): (a)**, the hernan4444 Kaggle dataset, for v1. See §4.6 for the later options.
- **CLEARED (v1.3).** TASK 004's PARTIAL is accepted: the Phase 7 importer drops and logs rows with undocumented status codes (0, 5, 33, 55; 540 rows) and duplicate `(user_id, anime_id)` pairs.
  - **Adult filter = OR:** exclude an anime if `Genres` contains "Hentai" OR `Rating` starts with "Rx".
  - **262 TV anime with unknown episode counts are excluded** for v1; note it in the Phase 8 report.
  - **Coverage gap:** the data has no anime after ~2020 (max MAL_ID 48,492; 0/10 recent shows present). README limitation. This is why Model B's show-level features come from AniList (§7).

## 5. MongoDB design

**Database:** `episode_three` (tests use `episode_three_test`).

**Free-tier constraints that shape the design:**
- Storage is capped at 0.5 GB, counting uncompressed BSON of all documents plus their indexes.
- 100 operations per second, so bulk writes use `insert_many` / `bulk_write`.
- Aggregations ignore `allowDiskUse`, pipelines max out at 50 stages, and in-memory sorts are limited to 32 MB, so heavy joins run in pandas instead.
- No server-side JavaScript.
- The cluster pauses after 30 days with zero connections.

**Conventions:** readable snake_case field names, dates stored as BSON dates in UTC, string `_id`s prefixed with their source so IDs from different sources never collide. Every sync uses upserts keyed on `_id`, so re-running never duplicates.

**Standing engineering rules (v1.1):** round trips from Nirav's network take 0.2–1.4 s (TASK 002), so:
- Any job that writes more than a few documents uses `insert_many` / `bulk_write`, never one write per document in a loop.
- Every network call has a timeout.
- Long jobs are resumable: they skip work already done and log progress (to `sync_runs`, or to files for probes).

### Collections

**`titles`**: one document per anime, show, or movie. Indexes: `media_type`; `mal_id` (to join with Kaggle data); `(season_year, season)`.
```json
{
  "_id": "anilist:154587",
  "source": "anilist",
  "media_type": "anime",
  "title": {"romaji": "Sousou no Frieren", "english": "Frieren: Beyond Journey's End"},
  "mal_id": 52991,
  "format": "TV", "episodes": 28, "duration_min": 24,
  "season": "FALL", "season_year": 2023,
  "source_material": "MANGA", "country": "JP", "is_adult": false,
  "genres": ["Adventure", "Drama", "Fantasy"],
  "tags": [{"name": "Elf", "rank": 95}],
  "main_studios": ["Madhouse"],
  "relations": [{"type": "SEQUEL", "id": "anilist:182255"}],
  "cover_url": "https://...",
  "current_average_score": 90,
  "current_popularity": 420000,
  "fetched_at": {"$date": "2026-10-05T10:00:00Z"}
}
```
TV and movies use IDs like `"tmdb_tv:1396"` / `"tmdb_movie:603"`, with Trakt IDs stored in `trakt_ids`. Values above are illustrative. *(v1.4: TMDB and Trakt are rejected; TV/movie ID formats come with the revised TASK 006.)*

**`my_entries`**: a read-only copy of Nirav's AniList list entries (v1.3; AniList is the tracker), one document per AniList list entry. From v1.4 it also holds hand-entered TV/movie entries (`source: "manual"`). References `titles` via `title_id`. Indexes: `title_id`, `mal_status_code`. Entries deleted on AniList are deleted here on the next sync. Documents are only written when their content changed, so a re-sync of unchanged data writes nothing.
```json
{
  "_id": "anilist_entry:123456789",
  "source": "anilist",
  "username": "npshetty25",
  "title_id": "anilist:154587",
  "anilist_status": "COMPLETED",
  "mal_status_code": 2,
  "repeating": false,
  "progress": 28,
  "score_100": 95,
  "started_at": {"year": 2024, "month": 1, "day": null},
  "completed_at": null,
  "created_at": {"$date": "2026-10-08T08:57:54Z"},
  "updated_at": {"$date": "2026-10-08T08:57:54Z"},
  "origin": "mal_import",
  "content_changed_at": {"$date": "2026-10-08T12:00:00Z"}
}
```
- **Deletion scope (v1.4):** the AniList sync reads and deletes only documents matching `source = "anilist"` AND `username` (`stored_entries_filter`, `entry_deletion_filter`). Manual entries can never match; a pure-function test proves it.
- **`content_changed_at` (v1.4, was `synced_at`):** the last time the document's content actually changed. Unchanged documents are not rewritten. Used on AniList entries and AniList titles; existing documents were migrated by `scripts/migrate_anilist_docs.py`.
- **`--stale` report (v1.4):** lists CURRENT/PAUSED entries that are either (a) imported and not edited since (`updated_at ≤ created_at + IMPORT_EDIT_GRACE_SECONDS`, 60 s), or (b) not updated for 180 days. Rule (b) applies to all entries, imported or not.
- **Status mapping (v1.3)** AniList → MAL training codes: CURRENT → 1, COMPLETED → 2, REPEATING → 2 (`repeating: true`), PAUSED → 3, DROPPED → 4, PLANNING → 6.
- `score_100` is `null` when unscored (AniList returns 0). `started_at`/`completed_at` keep AniList's FuzzyDate parts (any may be null) or are `null` when entirely unset; that is normal, not an error.
- **`origin` (v1.3, cutoff moved in v1.4):** "mal_import" if the entry was created before `MAL_IMPORT_CUTOFF`, else "anilist". The cutoff is now 2026-10-10 14:00 UTC: the full MAL history (12,735 entries) was imported at 12:59 UTC that day. It was 2026-10-08 10:00 UTC for the first, 139-entry import, since deleted on AniList. Imported entries have stale progress and mostly unset dates; statuses are roughly correct. Model B never uses progress or dates as features, so imported COMPLETED/DROPPED entries are usable as personal history.
- `sync_runs` (one per sync): `_id` "sync:anilist:<UTC ISO time>", job, username, started_at, finished_at, requests_used, counts (fetched, inserted, modified, unchanged, deleted, by_status, titles).
Status is normalized across sources to: `watching | completed | dropped | planning | paused | repeating`.

**`score_trends`**: time-series snapshots for Model A, stored as **one document per anime with an embedded array**. The array is naturally bounded (about 90–200 daily records while airing), so embedding is safe and lets one read return a show's whole history. Index: `(season_year, season)`.
```json
{
  "_id": "anilist:154587",
  "season": "FALL", "season_year": 2023,
  "snapshots": [
    {"date": {"$date": "2023-10-06T00:00:00Z"}, "episode": 4, "average_score": 89, "popularity": 152000, "in_progress": 98000, "trending": 1200}
  ],
  "n_snapshots": 112,
  "collected_at": {"$date": "2026-10-06T09:00:00Z"}
}
```

**`model_a_features`**: one row per eligible anime, built by an aggregation pipeline. Index: `split`.
```json
{"_id": "anilist:154587", "split": "train", "ep1_score": 87, "ep3_score": 89, "score_delta_1_3": 2,
 "ep3_popularity": 180000, "popularity_growth_1_3": 1.4, "ep3_in_progress": 120000,
 "episodes_planned": 28, "format": "TV", "source_material": "MANGA",
 "genres": ["Adventure", "Drama", "Fantasy"], "is_sequel": false, "prequel_finale_score": null,
 "label_finale_score": 91, "ep3_snapshot_date": {"$date": "2023-10-27T00:00:00Z"}}
```

**`mal_anime`** and **`mal_user_lists`**: Kaggle data, kept in separate collections so its source is always clear.
```json
{"_id": "mal:5114", "name": "Fullmetal Alchemist: Brotherhood", "type": "TV", "episodes": 64,
 "genres": ["Action", "Adventure", "Drama"], "source_material": "Manga", "mal_score": 9.19, "members": 2248456}
```
```json
{"_id": "mal_user:12345", "split": "train", "n_entries": 143,
 "entries": [{"anime_id": "mal:5114", "status": "completed", "episodes_watched": 64, "role": "history"},
             {"anime_id": "mal:1535", "status": "dropped",   "episodes_watched": 5,  "role": "target"}]}
```
User IDs are Kaggle's numeric IDs, stored as `"mal_user:<id>"` (v1.1); no usernames are ever stored. `role` marks each entry as feature history or a prediction target (section 7).

**`predictions`**: Index: `(model, title_id, created_at desc)`.
```json
{"model": "B", "model_version": "model_b_v1", "title_id": "anilist:21", "value": 0.31,
 "label": "drop_probability", "created_at": {"$date": "2026-11-01T12:00:00Z"}}
```

**`sync_runs`**: one log document per sync or collection run (job, started_at, finished_at, status, counts, errors). It makes long collections resumable and shows "last synced" on Home. Index: `(job, started_at desc)`.

**Later:** `listening_history` (unique index on `dedupe_key`), `playlists` (tracks embedded, `_id` = playlistId), `song_links` (anime ↔ theme songs).

### Aggregation pipelines we need
1. **Model A features** (snapshot selection PENDING TASK 003): `$unwind` snapshots → `$match` episode ∈ {1, 3} → `$sort` by date → `$group` by (anime, episode) taking `$last` → reshape into one row per anime → `$merge` into `model_a_features`.
2. **Model B user history stats:** `$unwind` entries → `$match` role = history → `$group` by user → count, drops, drop rate. Per-genre drop rates join `mal_anime` genres in pandas, to avoid large `$lookup`s and sorts on the free tier.
3. **Anime global drop rate (training users only):** `$unwind` → `$match` split = train → `$group` by anime_id.
4. **Dashboard:** status counts per media type (`$group`); planning list joined to latest predictions (`$lookup` with a small pipeline).

### Storage estimate (uncompressed data + indexes)
| Collection | Size estimate |
|---|---|
| `titles` (~6,500 docs × ~2 KB) | ~13 MB |
| `score_trends` (~1,000 × ~8 KB) | ~8 MB |
| `model_a_features` | <1 MB |
| `mal_anime` (~6,000 × ~0.5 KB) | ~3 MB |
| `mal_user_lists` (5,000 users × ~170 entries × ~95 B; v1.3, measured mean 170) | ~81 MB |
| `my_entries`, `predictions`, `sync_runs` | ~2 MB |
| *(later)* `listening_history` (~50 plays/day) | ~6 MB/year |
| Indexes (~15%) | ~15 MB |
| **Total** | **~131 MB** of 512 MB (26%) (v1.3; was ~145 MB) |

v1.1: an embedded entry such as `{"anime_id": "mal:5114", "status": "completed", "episodes_watched": 64, "role": "history"}` is about 95 B in BSON, because field names repeat in every entry. Readable names stay (they fit comfortably); shorten them only if usage passes 350 MB. **Measure with `dbStats` right after the Kaggle import.**

The sample dataset was measured (143 MB) and dropped in TASK 002.

**If usage passes 350 MB:** reduce Kaggle users to 3,000 → stop storing tags → move the Kaggle raw data to local CSVs and keep only aggregated features in Atlas → as a last resort, run a local MongoDB Community server for training data.

## 6. Data collection plan

- **Model A:**
  - Seasons **Fall 2018 to Summer 2026 (32 seasons)** (v1.2). Earlier seasons are excluded: releasing trend records are daily only from 2018-03-20, 2017 records are weekly with no popularity, and 2016 has none (TASK 003).
  - Eligible shows: format TV or ONA, 8–30 planned episodes, **episode duration ≥ 10 min** (v1.2; drops shorts and mini-dramas), Japan, not adult, popularity of at least 2,000 at the episode-3 snapshot. Roughly 30–40 per season; TASK 003 estimates ~820–1,150 usable, about 1,000.
  - **Collection method (v1.2) = option C:** `mediaTrends(mediaId_in: [~10 ids])` batches with date windows only: release start → M(4), and finale → finale + 7 days. Estimated ~1,300 requests ≈ 50 min at 27/min (+~10 min of 429 waits). It stores the least data, in the spirit of AniList's no-hoarding rule.
  - Collection is resumable: it skips anime already in `score_trends` and logs to `sync_runs`.
  - All of this depends on TASK 003 confirming the trend data exists.
- **Model B:**
  - Read `animelist.csv` in pandas chunks (it's too big for memory).
  - Keep TV anime only, drop adult titles, keep only completed (status 2) and dropped (status 4) entries.
  - Sample 5,000 users with at least 20 such entries (random seed 42). No API calls; about 30 minutes of local processing.
- **Nirav's data:** AniList is 1–3 requests per sync *(v1.4: now 26 requests, about 1 minute, for 12,735 entries at 500 per chunk)*. Trakt is about 4 requests. Run manually; scheduled later with Windows Task Scheduler.
- **YouTube Music (later):** poll every 3 hours while the PC is on; insert only items newer than the last seen top item.
- **Deduplication:** upserts on `_id` everywhere; a unique `dedupe_key` for listening history.
- **Anonymization:** Kaggle IDs are already numeric. If AniList users are ever collected (OPEN-1c), store `sha256(SALT + user_id)` with the salt in `.env`, never store names, and never publish the raw data.

## 7. The models

### Model A: Episode-3 predictor (regression)
- **Unit:** one eligible anime season.
- **Snapshots (v1.2, from the TASK 003 probe).** All days are JST days; a record "has a score" when `averageScore > 0`. `MediaTrend.episode` is non-null only on airing days (00:00 JST airings are marked on two consecutive days).
  - **Marker day M(n)** = the earliest of (a) the JST day of episode n's `airingSchedule.airingAt` and (b) the day of the first trend record with `episode = n`. Taking the earliest keeps snapshots before any reaction to episode n.
  - **ep3 snapshot** = the latest releasing record dated within **[M(4) − 3, M(4) − 1]** that has a score. Requires **M(3) < M(4)** (excludes premieres that release ep 4 together with ep 3). The 3-day window tolerates short AniList outages.
  - **ep1 snapshot** = the same rule with M(2): the latest scored releasing record within [M(2) − 3, M(2) − 1], requiring M(1) < M(2). Otherwise the ep1 features are missing and `multi_episode_premiere` = true.
  - `popularity` and `inProgress` come from the same record as the score.
- **Label (v1.2):**
  - **Primary:** `average_score` of the **last releasing record** (the finale-day record). Stored with `label_source`.
  - **Secondary (sensitivity, reported in Phase 6):** the score at **finale + 7 days**: the nearest scored record within M(final) + 5…+9 (from `releasing: false` records).
  - Store `current_average_score` for analysis only, never as a feature.
- **Exclusions:** no ep3 snapshot; no scored label; episode duration < 10 min.
- **Features (v1):**
  - `ep3_score`, `ep1_score`, `score_delta_1_3`
  - `ep3_popularity`, `popularity_growth_1_3` (ep3 ÷ ep1), `ep3_in_progress`
  - `episodes_planned`, `format`, `source_material`, `genres` (multi-hot)
  - `is_sequel`, `prequel_finale_score` (known before airing, so it's allowed)
  - v2 additions: main-studio prior (computed from training rows only), top tags.
- **Leakage rules:**
  - No value dated after the ep3 snapshot.
  - Never use `current_*` fields or the `stats` distributions.
  - Any prior (studio, genre) is computed from training rows only.
- **Split (by time):** train ≤ 2023 · validation 2024 · test 2025 through Summer 2026.
- **Baselines:** B1 "finale = ep3 score"; B2 training-set mean; B3 linear regression on `ep3_score` alone.
- **Candidate models:** Ridge, RandomForestRegressor, HistGradientBoostingRegressor. Pick by validation MAE, report test once.
- **Metrics:** MAE (points on a 0–100 scale; primary), RMSE, % of predictions within ±3 points.
- **Good enough:** test MAE at least 10% lower than B1. If not, publish the honest result anyway; "the episode-3 score is already a strong signal" is itself a finding.

### Model B: Drop predictor (classification)
- **Unit:** one (user, anime) entry with status completed or dropped. Label: dropped = 1.
- **History/target split:** each user's entries are randomly split 80% history / 20% target (seed 42). Features come only from history; rows are targets.
- **Features:**
  - **User:** history drop rate, number of history entries, smoothed drop rate for this anime's genres, average episode count of completed shows.
  - **Anime (v1.3): from AniList for BOTH training and inference anime.** Map the ~4,600 training anime with `idMal_in` (~95 requests, minimal fields): episodes, format, source, genres (multi-hot), average score (0–100), popularity (log scale), and the **drop share** from `stats.statusDistribution` (DROPPED / (COMPLETED + DROPPED)). Reason: the Kaggle data has no anime after ~2020, so `anime.csv` cannot describe Nirav's current shows; using one source for both keeps training and inference consistent.
  - **Flag:** the drop share of currently airing shows is immature (few people have finished or dropped yet).
  - **Phase 8 experiment:** a training-user smoothed drop rate `(drops + k × global) / (n + k)`, k ≈ 10, computed from training users only.
  - `statusDistribution` shape (TASK 005): a list of `{status, amount}` for CURRENT, PLANNING, COMPLETED, DROPPED and PAUSED. It can be selected inside `MediaListCollection` without a complexity error.
- **Leakage rules:** user features never see that user's target entries; global drop rates use training users only. Same-row `rating`/`watched_episodes` are never features.
- **Split:** by user (`GroupShuffleSplit`), 70/15/15 train/validation/test. No user appears in two splits.
- **Baselines:** B1 the anime's global drop rate; B2 the user's history drop rate; B3 logistic regression on both.
- **Models:** LogisticRegression, RandomForestClassifier, HistGradientBoostingClassifier.
- **Metrics:** ROC-AUC (primary), PR-AUC (classes are imbalanced), and precision/recall/F1 at a threshold chosen on validation.
- **Good enough:** ROC-AUC at least 0.03 above the best baseline on test.
- **Inference for Nirav:**
  - Map his AniList entries to MAL IDs via `titles.mal_id`.
  - Compute his user features from all his completed and dropped entries.
  - Predict for his planning list.
  - For currently airing shows, Model A's predicted finale score (converted from 0–100 to the 1–10 scale) replaces the community score. That's how the two models connect.
- **Known limits:** 2020 MAL users may behave differently from AniList users in 2026; the 0–100 vs 1–10 score scales differ; the history/target split is random rather than by time, because Kaggle has no per-entry timestamps.

### Storage, display, versioning (both models)
- **Model file:** `artifacts/models/model_a_v1.joblib` (git-ignored).
- **Report:** `reports/model_a_v1.json` (committed), containing features, data window, all metrics vs baselines, scikit-learn version, git commit, and creation date.
- A new version number whenever data or features change.
- Predictions are written to `predictions` with the model version; the dashboard shows the latest.

## 8. Streamlit dashboard

| Page | Shows | Uses |
|---|---|---|
| Home | Counts by status per type, recently updated entries, last sync times | `my_entries`, `sync_runs` |
| Tracker | Filterable table (Anime / TV / Movies tabs) with covers | `my_entries` + `titles` |
| Season Forecast | Current-season shows with ≥3 episodes: ep3 score, predicted finale ± test MAE | Model A, `score_trends` |
| Will I Finish? | Planning list ranked by drop probability, plus global feature importance | Model B, `predictions` |
| Model Report | Metrics vs baselines, error charts (Streamlit built-in charts) | `reports/*.json` |
| About & Credits | Credits (AniList, Kaggle dataset, TV source from the revised TASK 006), limitations | static |
| *(Later)* Music | Recent plays, top artists, playlists, theme links | `listening_history`, `song_links` |

## 9. Tech stack

| Tool | Purpose | Status |
|---|---|---|
| Python 3.13.5 + venv | Everything | installed |
| MongoDB Atlas (Free) + Compass | Database + GUI | set up |
| pymongo 4.18.2 | Python ↔ MongoDB | installed |
| python-dotenv 1.2.4 | Load secrets from `.env` | installed |
| requests | Call AniList, Trakt, TMDB, AnimeThemes | installed (TASK 003) |
| pandas 3.0.6 (+ numpy 2.5.3) | Data prep, Kaggle CSV chunks | installed (TASK 004) |
| pyarrow 25.0.1 | Write/read Parquet samples (fast, typed, compressed) | installed (TASK 004) |
| scikit-learn (+ joblib, included) | Models, metrics, saving models | Phase 6 |
| Jupyter (VS Code notebooks) | Exploration only | Phase 2 |
| Streamlit | Dashboard | Phase 9 |
| pytest 9.1.1 | Tests. **New tool:** the standard, simplest Python test runner; needed for section 12 | installed (TASK 004) |
| ytmusicapi | YouTube Music | Phase 10 |

For each phase, install the latest version, confirm it supports Python 3.13, and pin it in `requirements.txt`.

**Deliberately not used:** Java/JavaFX (dropped from priorities), FastAPI (Streamlit calls Python directly), Docker, LightGBM/XGBoost (scikit-learn is enough), SHAP (global importance first), Spotify (deprecated endpoints, restricted access), Jikan (unofficial; AniList covers it), ODMs like MongoEngine (raw pymongo teaches MongoDB better), schedulers like Airflow (Windows Task Scheduler is enough), the Kaggle CLI (manual download).

## 10. Project structure
```
episode-three/
├── .env                  # secrets (git-ignored)
├── .env.example          # placeholder keys (committed)
├── .gitignore
├── README.md
├── requirements.txt
├── docs/SPEC.md          # this document
├── devlog/NNN-kebab-title.md
├── episode_three/        # the Python package
│   ├── __init__.py
│   ├── config.py         # reads .env
│   ├── db.py             # MongoClient + get_db()
│   ├── clients/          # anilist.py, trakt.py, tmdb.py, ytmusic.py, animethemes.py
│   ├── sync/             # my_anime.py, my_trakt.py, music.py
│   ├── collect/          # score_trends.py, kaggle_import.py
│   ├── features/         # model_a.py, model_b.py
│   └── models/           # train_a.py, train_b.py, evaluate.py, predict.py
├── scripts/              # entry points: python -m scripts.<name>
├── app/                  # Streamlit: Home.py + pages/
├── notebooks/            # exploration only, never imported
├── tests/  (+ tests/fixtures/*.json saved API responses)
├── reports/              # model_*_vN.json (committed)
├── data/                 # raw/processed files (git-ignored)
└── artifacts/models/     # .joblib files (git-ignored)
```

**Naming conventions:**
- Files, functions, and variables: `snake_case`. Constants: `UPPER_CASE`. Classes: `PascalCase` (avoid classes unless needed).
- Collections: plural `snake_case`.
- Commit messages: `TASK 0NN: <what>`.
- Commits are small, one per logical change, and each one is a coherent, working step (v1.1).
- Run scripts from the repo root with `python -m scripts.<name>`.

## 11. Build phases

| # | Phase | Goal → definition of done | Nirav can explain afterwards |
|---|---|---|---|
| 1 | Foundation (TASK 002) | Python reaches Atlas; package skeleton; sample data removed | `.env` secrets, MongoClient, what counts toward 512 MB |
| 2 | Risk probes (TASKs 003–004) | Confirm AniList trend coverage; check Kaggle license and size | Why de-risk before building |
| 3 | Anime tracker | AniList client with rate limiter; idempotent sync of Nirav's list into `titles` + `my_entries`; first tests | GraphQL, rate limiting, upserts and idempotency |
| 4 | TV/movie tracker | *v1.4: our own tracker (TV via TVMaze, movies as minimal manual entries), with export/restore backups; revised TASK 006* | Source of truth and backups; scoped deletes |
| 5 | Model A data | Resumable trend collection; feature pipeline into `model_a_features` | Embedded arrays, aggregation pipelines |
| 6 | Model A training | Baselines + 3 models; report committed | Regression, MAE, time-based splits, leakage |
| 7 | Model B data | Kaggle sample into `mal_*`; history/target roles | Chunked processing, anonymization, data terms |
| 8 | Model B training | Baselines + 3 models; report committed | Classification, ROC-AUC vs PR-AUC, group splits |
| 9 | Dashboard (**MVP done**) | All MVP pages working | How the UI reads data and models |
| 10 | Music | History polling, playlists, theme links | Working with unofficial APIs, deduplication without timestamps |
| ~~11~~ | ~~TMDB + TV Model A (experimental)~~ | **Dropped in v1.4** (TMDB terms prohibit ML/AI use) | Why reading API terms is part of the engineering |
| 12 | Polish | README, diagram, GIF, tests | The whole story in 2 minutes |

## 12. Testing
- **pytest**, run with `python -m pytest`.
- **Unit tests (no network):** status normalization, snapshot selection (ep1/ep3/finale), feature functions, history/target splitting, score-scale conversion, rate-limiter wait calculation.
- **Parsing tests:** saved API responses in `tests/fixtures/` are parsed into our document shapes, so tests never call real APIs.
- **Integration test:** a write/read/delete round trip against `episode_three_test`, marked so it can be skipped when offline.
- **Model smoke tests:** load the saved model, predict one row, check the output range.
- **Evaluation checks:** split disjointness (no shared users, no overlapping seasons) asserted in code.

## 13. Deliverables
- **README:** problem → pitch → honest "what exists already" → features with screenshots → architecture diagram → how each model works → results table → limitations → setup instructions → credits/attribution.
- **Architecture diagram:** Mermaid in the README (GitHub renders it, no extra tool).
- **Results table template:**

| Model | Metric | Baseline B1 | B2 | B3 | Best model | Test result |
|---|---|---|---|---|---|---|

- **Demo GIF:** about 30 seconds of the dashboard, recorded with ScreenToGif (free, Windows).
- **Resume line:** *"Built a media tracker with two ML models — predicting an anime season's final score after 3 episodes (MAE [X] vs [Y] baseline) and whether a user will drop a show (ROC-AUC [A] vs [B]) — using MongoDB aggregation pipelines over [N] records and a Streamlit dashboard."*

## 14. Constraints
- No weekly-hour cap and no deadline (Nirav, 2026-10-04). The project is for his resume, not tied to any placement drive.
- Phases are sized for quality, not speed: tests in every phase from Phase 3 on, a short results write-up after each model, and no skipped evaluation steps.

## 15. How to teach Nirav (verbatim from his preferences)
From the current brief: *"I'm a complete Python beginner who must understand every decision well enough to explain it in a job interview."*

From the original project brief:
- "Teach me step by step. Give me ONE small step at a time, explain what each part of the code does in simple words, and wait for me to run it and report back before moving on."
- "Prefer simple, readable code over clever code. No unnecessary abstractions, classes, or design patterns unless I need them."
- "When I hit an error, help me understand WHY it happened, not just the fix."
- "Occasionally ask me a quick question to check I understood a concept (e.g. 'why do we store this as a nested array?')."
- "Don't introduce any tool or library that isn't in the tech stack below without asking me first and explaining why."
- "Remind me to commit to Git at the end of each working step, with a sensible commit message."
- "Don't write the whole project for me. I need to understand everything well enough to explain it in an interview."

*Adaptation now that Claude Code writes the code:* every task's "Teach Nirav" section carries the explanation. The developer comments code in plain English, and Nirav runs the acceptance commands himself.

## 16. Open questions and risks

| # | Question / risk | Recommendation |
|---|---|---|
| OPEN-1 | Model B data source | **Decided (v1.2):** hernan4444 Kaggle dataset for v1 (§4.6) |
| OPEN-2 | Do AniList trends go back to 2019 with per-episode scores, and what defines the finale label? | **Resolved (v1.2):** GO from Fall 2018 (90% of sampled shows usable); definitions in §7 |
| OPEN-3 | Does `airingSchedules` accept `mediaId_in` like `mediaTrends`? | Test with 1 request in Phase 5. If not, rely on trend markers (99% within ±1 day of the schedule) |
| OPEN-4 | Summer 2026 shows may not have reached finale + 7 days | Before counting a Summer 2026 show as usable, confirm finale + 7 days has passed |
| 3 | Kaggle license unclear | TASK 004 checks it. If restrictive, use option (c) with permission from AniList |
| 4 | AniList limit may change from 30/min | **Rewritten (v1.2):** `X-RateLimit-Remaining` does NOT predict 429s (a hidden limiter fires while it shows 20+). Keep the 2.2 s spacing and honour `Retry-After`; that is the real protection |
| 5 | Atlas 512 MB | Drop sample data now; check `dbStats` after each import |
| 6 | Atlas pauses after 30 idle days; no backups on Free | Use it regularly; add `mongodump` backups (MongoDB Database Tools) in Phase 12 |
| 7 / OPEN-7 | ytmusicapi auth: own Google Cloud OAuth client vs deprecated browser cookies | Decide in Phase 10; lean towards OAuth with own client |
| 8 | AnimeThemes JSON:API removal | Use GraphQL only |
| 9 | Trakt API and limit changes in 2026 | **Closed (v1.4):** Trakt rejected |
| 10 | TMDB episode ratings are current, not as-of-episode-3 | **Closed (v1.4):** TMDB rejected, TV Model A dropped |
| 14 | Nirav's ISP (Jio) blocks some sites at DNS level (themoviedb.org); Atlas DNS timeouts seen too | Encrypted DNS (DoH) on Windows; no IP pinning in code |
| 15 | Nirav's IP changes often (Atlas refuses with `TLSV1_ALERT_INTERNAL_ERROR`) | Add the current IP in Atlas → IP Access List when it happens; `check_db` explains the error |
| 11 | MAL 2020 → AniList 2026 shift; score-scale mismatch | State in the limitations section; compare Nirav's predicted vs actual drops over time |
| 12 | Atlas IP allowlist: home IP changes cause connection timeouts | TASK 002 documents the fix |
| 13 | Python 3.13 compatibility | Check each library at install time |
