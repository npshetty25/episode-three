# 008 — Airing markers M(n) and per-show trend windows (Phase 5, step 2)

- **Date:** 2026-10-17
- **Task:** TASK 008 from the instructor (spec v1.6 → v1.7)
- **Status:** Done. All 7 acceptance checks passed (2026-10-17); check 5 failed once on a DNS blip and was re-run by the developer (see below).

## Summary

For every eligible candidate we now find the days episodes 1–4 and the finale aired, store them in one day convention (00:00 JST as a UTC datetime), and derive the two date windows TASK 009 will request trends for, with the source of each recorded. The marker collection needs about 154 requests (one batch of up to 10 shows per request). Spec v1.7 records the pagination stop rule, the marker/window design and the popularity-drift note for TASK 010.

## Files changed (one commit each)

| Commit | Change |
|---|---|
| `7d3d570` | **Pagination stop rule.** `anilist.collect_pages` stops when `hasNextPage` is false OR a page has fewer rows than `perPage`; budget hook and page limit. The season listing and the airing probe now use it. 4 new tests; one old pagination test adjusted (a short page now ends the listing) |
| `24b2ac7` | **Marker + window functions** (`episode_three/collect/airing_markers.py`, all pure): `jst_day`, `day_from_fuzzy`, `make_batches`, `markers_from_schedule`, `trend_windows`, `marker_flags`, `candidate_update`, `estimate_pages`, `length_distribution`; 22 tests |
| `138b496` | **Marker collection** (`scripts/collect_airing_markers.py`): `--dry-run`, `--force`, developer `--max-batches`; one `bulk_write` per batch; resumable (`markers_fetched_at`), progress in `sync_runs` (job `airing_markers`); cap 190 requests per run. Also the optional `is_complete` early stop in `collect_pages` (see below) |
| `3e1b0d3` | **Trend budget estimate** (`scripts/estimate_trend_budget.py`, 0 requests) |
| *(this)* | spec v1.7 + this devlog |

## Design

- **Day convention:** `jst_day(unix)` returns the UTC datetime of that JST day's 00:00 JST (tested with an airing at 00:30 JST and one at 23:30 JST, both on the same JST day; 2018-10-05 JST = 2018-10-04T15:00:00Z). Markers and AniList's trend dates therefore compare directly.
- **Batching:** eligible candidates grouped by episode count N, sorted by start date, chunked at 10. One query asks for episodes `[1, 2, 3, 4, N]` for 10 shows: at most 50 rows.
- **Earliest row wins** per episode. Markers: `ep1..ep4` and `final` (the row whose episode equals `episodes`).
- **Windows (padded by a day):** w1 `[M(1) − 1, M(4) + 1]`, falling back to `[start − 1, start + 35]`; w2 `[M(final) − 1, M(final) + 10]`, falling back to `end_date`. Provenance in `marker_source`.
- **Status:** `excluded` if a window cannot be built (reasons `start_date_unknown`, `end_date_unknown`, or both = `markers_unavailable`); `pending` if finale + 9 days is still ahead (JST); else `ready`.
- **Flags** (recorded only): `non_monotonic`, `multi_episode_premiere`, `ep4_same_day_as_ep3`, `finale_row_missing`.
- **Plan (dry run, before the dev batch):** 1,431 eligible candidates → **154 batches** (21 different episode counts; 135 batches of 10 shows plus 19 partial ones). That is below the task's ~170 estimate.

## Verification (developer)

| Check | Result |
|---|---|
| `python -m pytest -q` | **93 passed, 1 deselected** (was 67), network blocked |
| `collect_airing_markers --dry-run` | 1,431 candidates → 154 batches, planned 154 requests, "0 AniList requests" |
| One full batch, live, nothing written (10 shows, N = 12) | **46 rows, 1 request**; 9 shows with 5 rows, 1 show with only 1 row; windows and sources as designed |
| Real script on the first batch (`--max-batches 1`, N = 8, 10 shows) | 1 request; 10 documents written; stored datetimes are UTC; progress document `airing_markers:…` written. This batch: 6 of 10 had schedule-based w1, 4 used the start-date fallback; flags `ep4_same_day_as_ep3` 1, `multi_episode_premiere` 1, `finale_row_missing` 2 |
| `estimate_trend_budget` on those 10 shows | works; the figures are meaningless for 10 shows scattered over years (their union window spans years); the real estimate needs all 1,431 sorted by start date |

Because 10 candidates now have markers, Nirav's run will process the other 1,421 (about 153 batches) and `--dry-run` will say so.

## Acceptance run by Nirav (PowerShell, 2026-10-17)

| # | Command | Result |
|---|---|---|
| 1 | `python -m pytest -q` | `93 passed, 1 deselected in 1.56s` ✅ |
| 2 | `collect_airing_markers --dry-run` | 1,421 candidates → **153 batches** (134 of 10 shows), planned 153 requests, "0 AniList requests" ✅ |
| 3 | `collect_airing_markers` | **153 requests** (cap 190), 0 × HTTP 429, 0 retries; **all 1,431 candidates ready**; w1 source: schedule 1,316, fallback_start_date 115; w2 source: schedule 1,353, fallback_end_date 78 ✅ |
| 4 | same again | `all candidates already have markers, 0 requests` ✅ |
| 5 | `estimate_trend_budget` | ⚠️ failed once: `Stopped: Your network couldn't look up the Atlas address (a DNS problem)` (Jio DNS timeout, the friendly message worked). Re-run by the developer a few minutes later: OK (below) |
| 6 | `check_db` | `episode_three` **17.51 MB (3.4%)**, was 16.94 MB ✅ |
| 7 | `git log -6` | the five TASK 008 commits ✅ |

### Status, sources and flags (1,431 eligible shows)

- **Collection status:** ready 1,431 · pending 0 · excluded 0. No show is pending: every Summer 2026 finale is already more than 9 days old (the latest probed finale was 2026-10-01).
- **Ready with a schedule-based w1: 1,316 (92%)**, above the ≥ 85% target.
- **Fallbacks:** w1 `fallback_start_date` 115 (8%); w2 `fallback_end_date` 78 (5%). No show lacked both sources, so none was excluded.
- **Flags** (recorded only): `multi_episode_premiere` 59 · `ep4_same_day_as_ep3` 20 · `finale_row_missing` 78 · `non_monotonic` 0.
- **Finale row missing:** 78 shows have no schedule row for episode N (finale episode ≠ `episodes`); they are exactly the 78 `fallback_end_date` windows. The query asks only for episodes 1–4 and N, so it cannot say why: the schedule may number the finale differently, or lack the row. (Question 4.)

### TASK 009 request estimate (from the stored windows, 0 requests)

| Window | Batches | Records (lower to upper) | Requests (lower to upper) |
|---|---|---|---|
| w1 (episodes 1–4) | 144 | 35,429 to 66,803 | 768 to 1,403 |
| w2 (finale) | 144 | 17,172 to 43,642 | 430 to 923 |
| **Total** | | | **1,198 to 2,326** |

- **w1 length in days (min / median / p95 / max): 3 / 24 / 37 / 108.** Schedule-based windows: min 3, median 24, p95 24, max 108. Fallback windows are always 37 days. The 3-day windows are double premieres; the 108-day one is a show whose first four episodes are spread over months (a long break).
- **How to read the range:** the lower bound counts one record per show per day of its OWN window; the upper bound counts one per show per day of the batch's UNION window (shows sorted by window start, 10 per batch). The real cost depends on the trend query: with `releasing: true` AniList returns records only while a show airs, which is close to the lower bound for w1. After the finale the records are `releasing: false`, so w2's secondary label (finale + 5…9 days) needs a query without that filter, which is nearer the upper bound for w2.

## Design decision worth explaining: `is_complete`

The instructor's stop rule is "hasNextPage is false OR rows < perPage". A batch of 10 shows with complete schedules returns **exactly 50 rows**, a full page, and AniList says `hasNextPage: true` on a full page (seen in TASK 007). Each such batch would cost a second, empty request. About 87% of schedules are complete, so roughly a quarter of the 135 full batches (about 35) would have done this, pushing the run from 154 toward the 190 cap.

Fix: `collect_pages` takes an optional `is_complete(rows)`. For the marker batches it is "the rows already contain every (show, episode) pair we asked for" (`covers_every_pair`): each show has at most one schedule row per episode, so nothing more can exist. If the rows contain duplicates or lack a pair, it still pages on. This adds a third, strictly safer stop to the stated rule.

## Failures and issues

1. **Two sloppy tests of mine** (an invalid date in a helper, a muddled assertion) failed the first run; fixed before committing.
2. **The shell mangled a long inline Python script** earlier in the session, so spec edits run from a file with exact-match assertions.
3. **No live failures:** no 429, no retries, no Atlas refusals this time.

## Decisions

- **`excluded` when either window cannot be built.** The task only named "neither → `markers_unavailable`". A show with no w1 cannot get an episode-3 snapshot, and one with no w2 cannot get a label, so no trend request is wasted on it. The more specific reasons `start_date_unknown` / `end_date_unknown` say which. (Question 1.)
- **Window from min/max of the four markers**, not ep1/ep4 directly, so an out-of-order schedule still produces `from < to`.
- **A request cap of 190 per run** (the task's hard cap is 200 including developer tests; developer use so far: 2).
- **`--max-batches`** is a developer-only option for testing with few requests.

## AniList requests

- **Developer: 2** (one live full batch, one real-script batch).
- **Nirav's run: 153** (exactly one per batch, so the `is_complete` early stop worked as designed: no empty second pages).
- **Total 155 of the 200 cap.** No HTTP 429, no retries.

## Questions for the instructor

1. Is `excluded` right when only w1 or only w2 is missing, or should such shows stay "ready" for the half that exists?
2. The `is_complete` early stop (above) goes beyond the stated stop rule. Keep it?
3. Batches are grouped by start date within an episode count, so shows from different years can share a batch when an episode count is rare (e.g. N = 8, 10 shows spanning years). Their TASK 009 windows are then far apart. TASK 009 should batch trend requests by window start, not by episode count; confirm.
4. 78 shows have no schedule row for episode N. Spend a few requests to look at their schedules (numbered N+1 or N-1, or missing?), or leave them on the `fallback_end_date` window?

## Teach Nirav (covered in the chat)

1. One day convention (00:00 JST stored as UTC) so comparisons never mix time zones.
2. Query design saves requests: grouping by episode count fetches episodes 1–4 and the finale for 10 shows in one request.
3. Provenance: recording where each marker came from makes every later exclusion explainable.

## Next

- The instructor rules on the four questions and sends TASK 009 (trend windows).
- **Recommendation for TASK 009:** batch trend requests by window start (sorted, 10 per batch), use `releasing: true` for w1 (cost near 768 requests) and a separate, narrower query for w2's finale + 5…9 days; collect w1 first and check the real record counts against this estimate before collecting w2.
