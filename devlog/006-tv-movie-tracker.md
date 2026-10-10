# 006 — TV & movie tracker with TMDB (Phase 4)

## Update 2026-10-10: Part C done (instructor: "proceed with Part C only")

**Rulings applied:** TMDB rejected (ML/AI clause), Phase 11's TMDB TV Model A dropped, and Parts B/D/E not started. A revised TASK 006 (TV via TVMaze, movies as minimal manual entries) follows.

### Changes (one commit each)

| Commit | Change |
|---|---|
| `daa72cc` | `anilist_sync.py`: entry docs get `source: "anilist"`; new `stored_entries_filter(username)` = `{source: "anilist", username}` and `entry_deletion_filter(username, ids)` = `{_id ∈ ids, source: "anilist", username}`. The sync reads and deletes only through these filters. `synced_at` → `content_changed_at` (entries and titles). `sync_anilist.py --stale` reads through the same filter, so manual entries never reach the AniList stale report. |
| `4203421` | 3 new tests: entry docs carry `source` + `content_changed_at`; **the deletion filter never matches a manual entry**, even with its `_id` on the delete list and the same username; manual entries are never planned for removal. A small pure-Python filter evaluator keeps them offline. |
| `a4beef2` | `scripts/migrate_anilist_docs.py`: idempotent migration over `episode_three` and `episode_three_test` |
| *(this update)* | `docs/SPEC.md` → **v1.4**; this devlog |

### Migration counts

| Database | AniList entries | `source` added | Entries renamed | Titles renamed | Left without `source` | Docs still with `synced_at` |
|---|---|---|---|---|---|---|
| `episode_three` | 139 | **139** | **139** | **139** | 0 | 0 |
| `episode_three_test` | 139 | **139** | **139** | **139** | 0 | 0 |

The second run changed **0** in both databases, so the migration is idempotent.

### Verification

- **`python -m pytest -q`:** `29 passed, 1 deselected` (was 26; +3 safety tests).
- **`sync_anilist.py --test` after the migration** (1 AniList request): entries 0 inserted, **2 modified**, 137 unchanged, 0 deleted; titles 139 modified.
  - Checked field by field against the not-yet-synced production copy: the 2 entries are Nirav's own AniList edits on 2026-10-09 (two shows CURRENT → COMPLETED, progress 0 → 13 and 0 → 8, `completed_at` 2026-10-09).
  - The 139 titles differ only in `current_popularity` (all 139), plus 1 score change. That is two days of AniList activity, not a migration artefact.
- **`--stale` (test DB):** reasons now read "imported, not edited since"; the list shrinks as Nirav edits entries (Uzumaki and Monster still listed; 136 of 139 without dates).
- **180-day rule confirmed:** `stale_entries` flags `untouched_import(doc) or updated_at < now − 180 days`. Rule (b) applies to every CURRENT/PAUSED entry. `test_stale_entries_and_missing_dates` covers a non-imported PAUSED entry flagged after 180 days.

### What failed

- **First migration attempt:** Atlas refused the TLS handshake (`TLSV1_ALERT_INTERNAL_ERROR`, IP not on the access list; Nirav's IP changes often). Nothing was written. Succeeded on retry.

### Full MAL history re-imported by Nirav (2026-10-10)

- **First production sync after Nirav updated AniList:** fetched **12,735**, inserted 12,735, **deleted 139**, titles inserted 12,596; **26 requests** (500 entries per chunk).
  - All 139 old entry IDs were gone on AniList, so the sync deleted them, as designed. The old 139-entry list is still in `episode_three_test`.
- **Analysis (database only):**
  - All 12,735 entries were created in the same minute (2026-10-10 12:59 UTC); 11,300 are scored.
  - Formats: TV 4,500, MOVIE 2,136, OVA 2,037, ONA 1,342, SPECIAL 1,205, MUSIC 828, TV_SHORT 633, unknown 54. 188 adult titles. Years from the 1940s to 2026.
  - **Nirav confirmed it is his real, full MAL history.**
- **Bug exposed:** the fixed `MAL_IMPORT_CUTOFF` (2026-10-08) labelled all 12,735 as `origin: "anilist"`, so `--stale` showed 0. *Fix:* the cutoff moved to 2026-10-10 14:00 UTC (commit `3ffa880`; tests still 29 passed).
- **Re-sync:** entries 0 inserted / **12,735 modified** (`origin` only) / 0 deleted; titles 52 modified (popularity); 26 requests.
  - `by_status`: COMPLETED 12,017, PLANNING 338, DROPPED 203, PAUSED 103, CURRENT 74.
  - `--stale`: **177** entries (all imported, not edited since).
  - 10,041 of 12,735 entries have no start or finish date.
- **Storage:** `episode_three` 15.20 MB, `episode_three_test` 0.31 MB, total 15.51 MB (3.0%).
- **AniList requests on 2026-10-10:** 1 (`--test` verification) + 26 (sync attempt that fetched, then failed on the Atlas IP allowlist) + 26 (first sync) + 26 (re-sync) = **79**.
- **The AniList doc's "11,000 most recently updated entries" cap did not bite:** chunked fetching returned all 12,735.
- **Atlas refused connections twice today** (IP changed). Nirav chose to keep the allowlist and re-add his IP when needed.

### Note on order

The new sync code expects `source: "anilist"` on stored entries. The migration ran **before** any sync with the new code, as required (a sync first would have rewritten all 139 entries, though never deleted any).

---

*(Original stop report below.)*

- **Date:** 2026-10-09
- **Task:** TASK 006 from the instructor
- **Status:** **STOPPED at Part B (terms check)**, before any code, as the task instructs. Three blockers need decisions; no feature work was done.

## Summary

The terms check found a material clause that TASK 006's context doesn't mention. The current TMDB terms restrict using TMDB content **for, or in connection with, machine-learning / AI applications**, and they explicitly restrict **training or validating ML systems** on TMDB content.

- **Phase 11** (an experimental TV Model A trained on TMDB episode ratings) falls under that restriction.
- **The Phase 4 tracker** (TMDB metadata shown only for display) is *not clearly* forbidden. But "in connection with … an ML-based Application" is ambiguous, because Episode Three is an ML app.

Two practical blockers come on top: there is no TMDB token in `.env`, and Nirav's ISP blocks TMDB at the DNS level.

## Part B: terms-check findings

### I could not read the official pages word for word

| Attempt | Result |
|---|---|
| Fetch `www.themoviedb.org/api-terms-of-use` and `/terms-of-use` | Nirav's network resolves `www.themoviedb.org` **and `api.themoviedb.org`** to **49.44.79.236**, a block address on his ISP (Jio). The connection is refused. |
| Real addresses via Google DNS-over-HTTPS (`www` → 18.161.229.x CloudFront, `api` → 108.157.4.51) | `api`: a real TMDB answer (`{"status_code":7,"status_message":"Invalid API key…"}` without a token), so **the block is DNS-only**. `www`: **HTTP 403 "Just a moment..."**, a CloudFront bot challenge that only a real browser passes. |
| Internet Archive copies | WebFetch may not read archive.org; direct download got HTTP 429 (rate-limited) |
| Web search (runs outside Nirav's network) | Worked, but returns **search-engine extracts of the official pages, not verified verbatim text** |

### Clauses found (search extracts; the instructor should confirm against the live pages)

1. **Caching:** you must not *"cache, for longer than 6 months, any information obtained through or from TMDB or the TMDB APIs"*. This matches the task context.
2. **Attribution:** the TMDB logo plus a notice in an "About" or "Credits" section, with the logo *"less prominent than the logo or mark that primarily describes the application"* and not implying endorsement.
   - **The notice wording differs between sources.** Older, widely quoted: *"This product uses the TMDB API but is not endorsed or certified by TMDB."* The task context: *"This [website, program, service, application, product] uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise approved by TMDB."* The current wording needs confirming.
3. **Non-commercial:** the service is *"made available only for personal, non-commercial use"* unless expressly authorised in writing.
4. **Other restrictions:** no *"cloak[ing] or conceal[ing]"* the identity of the application; no application that *"uses excessive bandwidth, degrades access to TMDB, or adversely impacts the stability of TMDB's systems"*.
5. **ML/AI, new and not in the task context:**
   - **API terms (reserved rights):** TMDB *"reserves all rights not expressly granted herein, including the right to make derivatives of the TMDB APIs or TMDB Content, or to use the TMDB APIs or TMDB Content in connection with, or for training, a machine learning or artificial intelligence based Application."* One search extract phrases this as a prohibition on using *"the TMDB APIs or TMDB Content in connection with, including for training, a machine learning (ML) or artificial intelligence (AI) based Application."*
   - **Site terms:** users must not *"train or validate a machine learning or artificial intelligence system (including large language models and Chatbots) using … the Materials, collect data sets containing … the Materials for such training or validation, or provide archived or cached data sets containing … the Materials"* to others.
6. **Staff clarification (forum, not a contract term):** in the TMDB Talk thread "Clarification needed — 'training an AI/ML system'" (July 2026, `themoviedb.org/talk/6a5e284be6125cf4396873a6`), a TMDB staff member reportedly said a **personal, non-commercial portfolio recommendation feature** does not count as the restricted use, provided TMDB is attributed.
7. **Public GitHub project:** no clause found about publishing *code*. But committing real TMDB responses (for example as test fixtures) would keep TMDB data beyond 6 months and redistribute it. So fixtures must be **hand-made**, as the task already plans.

### What this means for our design

| Part of the plan | Assessment |
|---|---|
| Phase 4 tracker (TMDB metadata for display only) | **Not clearly forbidden**, but ambiguous under "in connection with … an ML-based Application". Proposed mitigation: a hard rule that **TMDB data never enters any model, feature, training or validation set**; models read only AniList/Kaggle-derived data; TMDB titles stay clearly separated; credits on the About page. |
| Model B inference | Must **exclude manual TV/movie entries** (they would bring TMDB genres and other fields into model features). |
| Phase 11 experimental TV Model A on TMDB episode ratings | **Restricted** (training/validating on TMDB content). Recommend removing it from scope, or finding a different data source. |

## Other blockers

1. **No `TMDB_API_READ_TOKEN` in `.env`.** Only `MONGODB_URI`, `MAL_DATA_DIR` and `ANILIST_USERNAME` are present. Nirav needs a TMDB account and an API Read Access Token.
2. **DNS block on Nirav's network.** `api.themoviedb.org` resolves to the block address; plain lookups via 8.8.8.8 also returned nothing, which suggests interception. The fix belongs on the machine: **Windows 11 encrypted DNS (DNS over HTTPS)**. Pinning IP addresses in code was rejected: brittle, and it would hide the problem.

## Requests used

- TMDB: **1** unauthenticated request to `api.themoviedb.org/3/configuration`, to prove reachability at the real address (budget 30).
- `www.themoviedb.org`: 2 page fetches (HTTP 403 bot challenge).
- AniList: 0.

## Files changed

- This devlog only. No code, as required by "Part B FIRST" and "STOP and report".

## Decisions

- **Stopped instead of building:** the verbatim terms could not be read, and a material ML/AI clause the instructor didn't list may cover the project. The ruling belongs to the instructor.
- **Part C (AniList deletion scoping + `synced_at` → `content_changed_at`)** doesn't depend on TMDB. Holding it for the instructor's word, since TASK 006 orders Part B first.

## Questions for the instructor

1. Read the live TMDB API terms and site terms (you have web access outside Jio's block) and confirm the ML/AI wording and the current attribution notice.
2. Proceed with Phase 4 under a strict "TMDB data never enters any model" rule (with Model B excluding manual entries)? Or change approach: a different metadata source, or a TV/movie tracker without TMDB?
3. Remove Phase 11's TMDB-based TV Model A from scope?
4. May Part C go ahead now, independently of the TMDB decision?

## Next

- Nirav: switch Windows to encrypted DNS (fixes the TMDB block, and probably the earlier Atlas DNS timeouts). Create the TMDB token only if Phase 4 continues with TMDB.
- Instructor rules on questions 1–4.
