# 009 — Trend collection, window 1 (premiere → episode 4) (Phase 5, step 3)

- **Date:** 2026-10-18
- **Task:** TASK 009 from the instructor (spec v1.7 → v1.8)
- **Status:** Built and verified by the developer on one real batch. **Waiting on Nirav's acceptance run** (the 5-batch pilot, the full w1 collection, the marker comparison). The pilot numbers, final counts and request totals come from that run.

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

- Nirav runs the acceptance commands (STOP after step 3 if records are over 1.3× the estimate) and pastes the output; the real numbers are added here.
