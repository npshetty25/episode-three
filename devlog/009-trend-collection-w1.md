# 009 — Trend collection, window 1 (premiere → episode 4) (Phase 5, step 3)

- **Date:** 2026-10-18
- **Task:** TASK 009 from the instructor (spec v1.7 → v1.8)
- **Status:** **Paused at the pilot by the 1.3× stop rule** (the instructor's instruction). Pilot done and stored (50 shows); the full run, the marker comparison and the remaining checks wait for the instructor's ruling.

## Summary

The collector fetches each show's daily score trends for window 1 into `score_trends` (`snapshots_w1`), batched by window start, resumably and within a stated budget. A pilot mode and a 1.3× stop rule check the real cost before the full run. A 0-request script compares the trend episode markers with the schedule markers and counts the shows that cannot give an episode-3 snapshot. Spec v1.8 records the five rulings.

## Files changed (one commit each)

| Commit | Change |
|---|---|
| `a8280b6` | `episode_three/collect/score_trends.py` (pure functions) + 14 tests + a hand-made 2-page fixture with a same-day tie across shows: `make_w1_batches`, `union_window`, `estimate_batch_records`, `parse_trend_rows` (dedupe on `(mediaId, date)`, counted), `trim_to_window`, `build_updates`, `trend_marker_days`, `day_difference`, `earliest`, `ep3_snapshot_check`, and `fetch_trends` (the one network function) |
| `c5372eb` | `scripts/collect_score_trends.py` (`--window w1`, `--limit-batches`, `--dry-run`, `--force`) |
| `c01eaae` | `scripts/check_trend_markers.py` |
| `2c66169` | creates the `(season_year, season)` index on `score_trends` |
| *(this)* | spec v1.8 + this devlog |

## Design

- **Query:** `mediaTrends(mediaId_in, date_greater, date_lesser, releasing: true, sort: [MEDIA_ID, DATE])`. Verified by GraphQL introspection (1 request, because docs.anilist.co returns HTTP 403 to scripts): `MediaTrendSort` contains `MEDIA_ID` and `DATE`; `date_greater` and `date_lesser` are `Int`.
- **Why `[MEDIA_ID, DATE]`:** sorting by DATE alone leaves ties between the 10 shows of a batch on the same day; an unstable tie order can skip or repeat rows across pages. `MEDIA_ID` breaks the tie. We still dedupe on `(mediaId, date)` and count duplicates.
- **Batching:** ready shows sorted by w1 start, 10 per batch, union window; w1 longer than 40 days gets a batch of its own. Plan: **146 batches** (143 normal + 3 long-window shows alone), estimated 767 (own windows) to 1,401 (union windows) requests.
- **Atomic batches:** a batch is written only after ALL its pages arrived. `score_trends` is written first, and the candidate's `w1_status` LAST, so a crash in between just redoes the batch.
- **Statuses:** `w1_status` is `collected` (at least one record inside the show's own window) or `no_records`.
- **Budget:** cap 1,100 for the task. The script reads the requests used by earlier runs from `sync_runs` (job `score_trends_w1`), so the pilot and any developer test count automatically. After 5 batches in a run, it stops if actual records exceed 1.3× the lower estimate.
- **Pagination:** the shared helper (`hasNextPage` false OR rows < `perPage`).

## How `is_complete` decides (TASK 008) and why it was not used here

For the marker batches (TASK 008), `is_complete(rows)` is `covers_every_pair`: true when the rows contain every (show, episode) pair asked for. Each show has at most one schedule row per episode, so once every pair is present nothing more can exist; a page of exactly 10 × 5 = 50 rows then needs no second request. If a pair is missing or rows repeat, it keeps paging. Tests: `test_a_batch_that_covers_every_pair_needs_no_second_page` and `test_is_complete_skips_the_request_a_full_page_would_trigger`. Trend queries have no fixed row count, so they use only the stop rule.

## 1,421 vs 1,431

There are **1,431 eligible shows**. In TASK 008 I first ran the marker script on one batch of 10 as my own developer test, so those 10 already had markers; Nirav's run then processed the other **1,421** (153 batches), and together all 1,431 had markers. The same thing happens now: the 10 shows of my one-batch developer test (the first batch by window start) are already collected, so Nirav's dry run shows **1,421 shows**, not 1,431.

## Verification (developer)

| Check | Result |
|---|---|
| `python -m pytest -q` | **105 passed, 1 deselected** (was 93), network blocked |
| `collect_score_trends --window w1 --dry-run` | 1,431 shows → 146 batches, union width min/median/p95/max 25 / 31.5 / 109 / 119 days, planned minimum 146, estimate 767 to 1,401 |
| Real script, one batch (`--limit-batches 1`) | 10 shows, **336 records vs estimate 292 to 470 = 1.15× the lower estimate**, **7 requests**, 0 duplicates, 0 × 429; documents and candidate statuses written correctly (first show: 23 snapshots, `w1_status: collected`) |
| `check_trend_markers` on those 10 shows | 20 comparable markers, **100% within ±1 day** (14 exactly equal, 6 one day earlier); trend markers present: ep1 0, ep2 8, ep3 9, ep4 9 of 10; 3 of the 4 fallback shows rescued (eps 3 and 4 present); 2 of 10 lack an ep3 snapshot (1 `no_m4`, 1 `no_scored_record`) |

**Reading the pilot batch:** about 48 records per request (336 / 7), so the cost is roughly records ÷ 48. At 1.15× the lower estimate (35,429 records) the full w1 collection is about 40,700 records, **about 850 requests**, inside the 1,100 cap.

## Pilot run by Nirav (PowerShell, 2026-10-18): STOPPED by the 1.3× rule

| Check | Result |
|---|---|
| `python -m pytest -q` | `105 passed, 1 deselected in 1.37s` ✅ |
| `--dry-run` | 1,421 shows → 145 batches (142 normal + 3 long alone), union width 25 / 31 / 109 / 119 days, estimate 761 to 1,391, "earlier runs used 7" (my developer batch) ✅ |
| `--limit-batches 5` | 50 shows, **1,771 records vs estimate 1,304 (own windows) to 2,340 (union windows) = 1.36× the lower estimate**, 39 requests in 1.4 min, 0 × 429, 0 retries, 0 duplicates. **STOPPED** (limit 1.3×) ✅ as designed |

Per batch (records, estimate lower to upper, requests): 217 (240–250) 5 · 339 (253–380) 7 · **550 (286–920) 12** · 350 (246–410) 8 · 315 (279–380) 7. Status afterwards: collected 59, no_records 1, not collected 1,371; snapshots per show min 0 / median 22 / max 36.

### Why 1.36×: an offline model of the real batches (0 requests)

With `releasing: true`, AniList returns a record for every day a show is airing INSIDE the batch's union window, not only inside the show's own w1 window. A show airing for 12 weeks inside a 92-day union window returns up to 92 days of records, and we trim most of them away. So the right estimate is not "own-window days" (the lower bound) but: for each show, the overlap of the union window with the show's airing period (day after episode 1 to the finale).

That model reproduces all six real batches (developer batch + pilot): predicted 357 / 227 / 349 / **549** / 360 / 322 vs actual **336 / 217 / 339 / 550 / 350 / 315** (within 6%). Against it the pilot is about 1.0×, not 1.36×. About a third of the downloaded rows are trimmed away (trimmed snapshots stored: 260 / 217 / 232 / 199 / 225 / 225).

### Projection for the whole of w1 (model, 0 requests)

| Batching | Batches | Records | Requests (all 1,431 shows) |
|---|---|---|---|
| As built (10 per batch, sorted by start) | 146 | 43,612 | **938** |
| Union width capped at 50 days | 179 | 38,937 | 867 |
| Union width capped at 40 days | 213 | 37,516 | 857 |
| Union width capped at 35 days | 323 | 33,359 | 834 |
| Union width capped at 30 days | 353 | 32,652 | 828 |
| One show per batch | 1,431 | 30,658 | 1,434 |

Requests already used: 47 (my 8 + the pilot's 39). The remaining shows need about 900 more as built, so about **950 in total (cap 1,100)**. A 40-day width cap would save about 80 requests (9%) and download 14% fewer rows, at the cost of more batches and a change to the batching function.

### The one `no_records` show

`anilist:101500`: an ONA with 11 episodes released **all at once** (start date = end date = 2018-10-18). It has no daily airing history, hence no records in w1. A binge-released show cannot give an episode-3 snapshot. Suggested rule for TASK 010: exclude when `start_date == end_date` (or M(1) = M(final)), with reason `binge_release`.

## Findings

1. **The docs site blocks scripts** (HTTP 403), so enum values and argument types come from GraphQL introspection instead.
2. **Trend episode markers rarely include episode 1** (0 of 10): the records start the day after episode 1 airs, as TASK 003 found. Episodes 2–4 are present in 8–9 of 10.
3. **The trend marker never differs from the schedule by more than a day** in this sample (the 00:00 JST double-marking explains the −1s).

## Failures and issues

None live: no 429, no retries, no duplicates, no Atlas refusals during my tests.

## Decisions

- **The 1.3× check uses the LOWER estimate** (each show's own window days): with `releasing: true` AniList returns records only while a show airs, which is close to the own-window total.
- **Long-window shows are isolated one per batch** (3 shows; their windows span up to 108 days), so they cannot stretch the union window of ten others.
- **The request cap subtracts earlier runs' usage** from `sync_runs`, so the pilot and my developer batch count without a separate setting.
- **The index on `score_trends`** is created by the collector (it had been described in the spec only).

## AniList requests

- **Developer: 8** (1 introspection, 7 for one real batch). They count toward the 1,100 cap through `sync_runs`.
- **Expected for Nirav's runs:** the pilot about 35, the full run about 850, so about 890 in total.

## Questions for the instructor

1. The dry-run estimate of union widths has a p95 of 109 days, but with `releasing: true` the width of the date filter does not change the number of records returned. Is that the right reading, or should batches be capped by union width as well as by count?
2. Episode-1 trend markers are almost always absent; the schedule is the only source for M(1). Acceptable, since the ep1 snapshot window uses M(2)?
3. For w2 (no releasing filter) the projection is about 923 requests on union windows. Should w2 shrink the window to `[finale − 1, finale + 10]` only for the label days we use (finale, and finale + 5…9), or keep the contiguous window?

## Teach Nirav (covered in the chat)

1. Stable sorting for pagination, and the tie-breaker.
2. Pilot before the full run.
3. Batch atomicity.

## Next

- The instructor rules on the 1.36× stop and the three questions below (plus question 4), then the full run continues; the remaining acceptance steps (full run, second run, `check_trend_markers`, `check_db`) follow.

4. **Stop rule yardstick:** the 1.3× rule compares with the own-window (lower) estimate, which the model shows is too low whenever a union window is wide. Continue as built (about 950 requests in total), or cap batches by union width (about 40 days, about 900 in total), and which yardstick should the rule use from now on?
5. **Binge-released shows** (start date = end date) have no airing history: exclude with reason `binge_release` in TASK 010?
