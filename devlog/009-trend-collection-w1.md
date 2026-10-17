# 009 — Trend collection, window 1 (premiere → episode 4) (Phase 5, step 3)

- **Date:** 2026-10-18
- **Task:** TASK 009 from the instructor (spec v1.7 → v1.8)
- **Status:** Done (2026-10-19). Full w1 collection complete: all 1,431 ready shows have a `w1_status`. All acceptance checks passed; check 4 (second run) hit a Jio DNS timeout on Nirav's machine and was re-run by the developer (0 requests).

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

## Continuation (2026-10-19): width cap, model-based stop rule

### Files changed (one commit each)

| Commit | Change |
|---|---|
| `45d3c01` | `make_w1_batches`: new batch at 10 shows OR when the next show would widen the union past `W1_MAX_UNION_DAYS = 40`; long windows stay alone. `predict_batch_records` (airing-overlap model), `predicted_requests` (`records // 50 + 1`), `should_stop`, `is_binge`; fixture `trend_pilot_batches.json` (the 6 real batches: show windows, ep1 marker, w2 start, actual records) |
| `45b2883` | Collector: model-based stop rule (after ≥ 10 batches stop if cumulative actual / predicted > 1.15; both totals logged to `sync_runs`), the old 1.3× rule removed, dry run prints batches / predicted records / predicted requests / union-width distribution, w2 projection |
| `4db063e` | `check_trend_markers`: `m1_unknown` count, binge sub-label `m3_not_before_m4 (binge)` |
| `ae34f4e` | Spec v1.8 additions (items 6–10) |

### Verification (developer, 0 requests)

| Check | Result |
|---|---|
| `python -m pytest -q` | **114 passed, 1 deselected** (was 105) |
| Model vs the 6 real batches (test, each within 10%) | passes; the model was within 6% for each (357/227/349/549/360/322 predicted vs 336/217/339/550/350/315) |
| `predicted_requests` vs real request counts | 336→7, 217→5, 339→7, 550→12, 350→8, 315→7: all six match (an exact multiple of 50 costs one extra empty page) |
| `collect_score_trends --window w1 --dry-run` | **1,371 shows → 204 batches** (201 normal + 3 long alone); union width min/median/p95/max 3 / 34 / 40 / 108; **predicted 35,602 records, 818 requests**; earlier runs used 46 in `sync_runs` (47 with my introspection request), so about **864 in total** (cap 1,100) |
| w2 projection (same model) | 171 batches (finale-date order, 10 per batch, 40-day cap), 29,173 records, **about 689 requests** |
| `check_trend_markers` on the 59 shows collected so far | 149 comparable markers, **98.7% within ±1 day** (88% exactly equal); 11 fallback shows, 8 rescued (eps 3 and 4 present); 5 of 59 lack an ep3 snapshot (2 `no_scored_record`, 2 binge, 1 `no_m4`); `m1_unknown` 8 of 59 |

No requests were made in this continuation (0 developer requests); the task total stays at the 47 already used.

## Acceptance run by Nirav (PowerShell, 2026-10-19)

| # | Command | Result |
|---|---|---|
| 1 | `python -m pytest -q` | `114 passed, 1 deselected in 1.47s` ✅ |
| 2 | `--dry-run` | 1,371 shows → 204 batches, predicted 35,602 records / 818 requests, "0 requests" ✅ |
| 3 | `collect_score_trends --window w1` | all 204 batches, **792 requests** (earlier runs 46, total 838 of 1,100), **32.9 min**, 0 × HTTP 429, 4 retries (network errors, recovered). **Actual 33,427 vs predicted 35,602 records: ratio 0.939**; cumulative ratio stayed at 0.94–0.97 throughout, so the stop rule never fired. 0 duplicates removed ✅ |
| 4 | same again | ⚠️ failed on Nirav's machine with a Jio DNS timeout to Atlas (friendly message, "AniList requests used: 0"). **Re-run by the developer: "all shows already collected, 0 requests"** ✅ |
| 5 | `check_trend_markers` | see below ✅ |
| 6 | `check_db` | `episode_three` **20.98 MB (4.1%)**, was 17.51 MB (+3.5 MB) ✅ |
| 7 | `git log -4` | the TASK 009 commits ✅ |

**Requests for the whole task:** developer 8 (1 introspection + 7) + pilot 39 + full run 792 = **839 of 1,100**.

### The model held

Actual records were 6% below the prediction (33,427 vs 35,602). The model over-predicts shows that have no trend records at all (it assumes every airing day has a record), e.g. batch 190: 52 actual vs 230 predicted. The 1,371-show plan was predicted at 818 requests and cost 792 (3% under).

### Collected vs no_records

- **w1 status of the 1,431 ready shows: collected 1,377, no_records 54** (3.8%). `score_trends`: 1,431 documents; snapshots per show min 0 / median 22 / max 105.
- **52 of the 54 are ONAs and 2 are TV.** 32% of all 162 ONAs have no records, against 0.2% of the 1,269 TV shows.
- **48 of the 54 are binge releases** (start date = end date, or M(1) = M(final)); 38 used the start-date fallback window. Binge status does not always mean no records: 19 of the 110 collected ONAs are binge too.
- **The 6 not-binge ones:** three ONAs with missing schedule data (`100780` has no finale row, `119964` no ep 1, `146722` neither; `146646` no finale row), and two ordinary weekly TV shows: `130402` (Jan–Mar 2021) and `169228` (Apr–Jun 2026; its w1 window, Apr 9–18, lies inside the known AniList outage of 2026-04-03 → 04-19). `130402` has no explanation yet.
- **ids (format, episodes):** 101500 (ONA 11), 105807 (12), 105200 (10), 100663 (13), 100891 (12), 111131 (12), 110686 (9), 100780 (12), 108598 (12), 107067 (12), 108522 (13), 112686 (12), 119964 (8), 112357 (10), 125428 (12), **130402 (TV 12)**, 127399 (12), 124195 (12), 138060 (9), 109946 (13), 127619 (10), 125447 (11), 120377 (10), 146722 (26), 125440 (8), 153930 (12), 151803 (12), 135660 (8), 150653 (12), 154983 (10), 135429 (8), 163137 (10), 147729 (12), 146646 (27), 146638 (12), 159926 (15), 99088 (8), 170206 (8), 130706 (12), 155015 (8), 177106 (8), 169692 (16), 177814 (8), 184560 (14), 136880 (12), 150654 (18), 177887 (12), 186043 (12), 184642 (9), 202955 (20), 187267 (12), 176509 (13), **169228 (TV 14)**, 213847 (8); every other id is an ONA.

### Marker comparison on the full set (1,377 collected shows; 0 requests)

- **Trend markers present** (a record with `episode = n` inside w1): ep1 54, ep2 1,233, ep3 1,302, ep4 1,329.
- **Trend minus schedule, in days (3,805 comparable markers): 99.4% within ±1** (3,782); exactly equal 85.4% (3,251); −1 day 13.6% (519, the 00:00-JST double-marking); beyond ±1: 23 markers (0.6%): −21 ×1, −8 ×2, −7 ×10, −6 ×5, −2 ×3, +2 ×1, +7 ×1 (break-week schedule/trend disagreements). Per episode: ep1 98.0% (49 compared), ep2 99.5%, ep3 99.4%, ep4 99.3%.
- **Fallback shows:** 77; **rescued by trend markers (eps 3 AND 4): 42 (55%)**; all of eps 1–4: 3.
- **Episode-3 snapshot check** (M(n) = earliest of schedule and trend marker): **ok 1,311 of 1,377 (95.2%)**; lacking 66: `no_scored_record` 30, `m3_not_before_m4 (binge)` 19, `no_m4` 7, `m3_not_before_m4` 6, `no_m3` 4. By source: schedule-based w1: ok 1,270, no_scored_record 24, m3_not_before_m4 6; fallback w1: ok 41, binge 19, no_m4 7, no_scored_record 6, no_m3 4.
- **`m1_unknown`: 57 of 1,377** (4.1%): ep1 features null, show kept.
- (The 54 `no_records` shows are not in these 1,377; they cannot give an ep3 snapshot either, so the model will lack at least 66 + 54 = 120 shows, about 8% of the 1,431.)

### Projection for w2 (same model; 0 requests)

171 batches (finale-date order, 10 per batch, 40-day cap, no releasing filter: one record per show-day of the union window), **29,173 records, about 689 requests.** Total task cost would then stay near 839 + 689 ≈ 1,528 across TASK 009 and the w2 task, but w2 gets its own budget.

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

- The instructor sends the next task (w2 collection, then the feature pipeline). **Recommendation:** collect w2 with the same batching (finale date, 40-day cap, about 689 requests); skip the 54 `no_records` shows for w2 (no w1 means no features); decide in TASK 010 whether ONAs with no daily record are excluded as a class.
- (Questions 1–5 below were answered by the instructor's ruling: width cap 40 days, model-based stop rule, binge → M(3) < M(4), m1_unknown keeps the show, w2 one contiguous window.)

4. **Stop rule yardstick:** the 1.3× rule compares with the own-window (lower) estimate, which the model shows is too low whenever a union window is wide. Continue as built (about 950 requests in total), or cap batches by union width (about 40 days, about 900 in total), and which yardstick should the rule use from now on?
5. **Binge-released shows** (start date = end date) have no airing history: exclude with reason `binge_release` in TASK 010?
