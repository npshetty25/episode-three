# 010 — Trend collection, window 2 (finale → finale + 10) and the labels (Phase 5, step 4)

- **Date:** 2026-10-19
- **Task:** TASK 010 from the instructor (spec v1.8 → v1.9)
- **Status:** Done. Full w2 run and label check complete (results below).

## Summary

The collector now has `--window w2`, which fetches the label window without the releasing filter. A cost model picked the union-width cap. Label functions (primary, secondary, flags) read only `snapshots_w2`. A 0-request script flags shows whose trend and schedule markers disagree.

## Files changed (one commit each)

| Commit | What |
|---|---|
| `6347caa` | w2 batching, `union_window`, `w2_cap_comparison`, `choose_w2_cap`, label functions with transition / no-transition fixtures |
| `f898bc5` | Collector `--window w1\|w2`, cap table in the dry run, `skipped_no_w1`, stop rule after 5 batches, cap 800 minus 1 reserved |
| `a6fa110` | `check_labels` (counts, flags with example ids, fallback shows separately, secondary − primary distribution) |
| `4a83031` | `probe_trends_single` (1 request), `flag_marker_disagreement` (0 requests) |
| `fb6ffd1` | `W2_MAX_UNION_DAYS = 14` after the real comparison; one test updated (it assumed cap 40) |

## Decisions

**The cap came from the model.** Predicted for 1,377 shows:

| cap (days) | batches | records | requests |
|---|---|---|---|
| 12 | 601 | 16,524 | 666 |
| **14** | **323** | **18,658** | **548** |
| 20 | 212 | 22,081 | 568 |
| 40 | 165 | 26,957 | 638 |

Narrow caps waste requests on many small batches (each costs at least one); wide caps download many show-days nobody needs. 14 is the minimum.

**Labels never leak into features.** Label data lives only in `snapshots_w2`. TASK 011 will assert no feature code reads it.

**Nothing is excluded here.** Flags are diagnostics; ONA is not excluded as a class.

## Checks run by the developer

- `pytest`: 127 passed offline.
- `collect_score_trends --window w2 --dry-run`: 1,377 shows, 54 `skipped_no_w1`, 323 batches, 18,658 predicted records, 548 predicted requests.
- One live w2 batch (`--limit-batches 1`): 1 show, 10 records (predicted 12), 1 request, 0 × 429; `check_labels` found both labels, no flags.
- `flag_marker_disagreement`: 16 of 1,377 (1.2%); ep1 1, ep2 6, ep3 7, ep4 9.

## Acceptance run (Nirav, 2026-10-19)

- `pytest` 127 passed. Dry run: 1,376 shows (the 54 `skipped_no_w1` were already marked by my test run), 322 batches, 547 predicted requests.
- Full run: **502 requests, 18.5 min, 0 x 429, 0 retries**, 0 duplicates. Actual 15,643 vs predicted 18,646 records (ratio **0.839**, steady 0.84-0.85 from batch 10 on; the stop rule never fired). The model over-predicts because it assumes a record for every show-day, and AniList has none for some days. Total w2 requests: 503 of 800. Second run: 0 requests.
- w2_status: collected 1,374, `no_records` 3 (anilist:179062, 198374, 187062; TV, 12-13 eps), skipped_no_w1 54. Storage 22.8 MB of 512.
- `check_labels` (1,374 collected): primary label 1,340 (97.5%), secondary 1,356 (98.7%), both 1,327 (96.6%), neither 5. Flags: no_transition 23, finale_episode_mismatch 32, label_at_window_edge 563. marker_disagreement 16.
- Fallback_end_date shows (40): primary 26 (65.0%), secondary 38 (95.0%), no_transition 7, mismatch 11, edge 12. Schedule shows (1,334): primary 98.5%, secondary 98.8%.
- Secondary minus primary: mean +1.59, median +1, within +-1 48.8%, within +-3 89.2%, largest 10. The secondary label is systematically higher: scores keep rising after the finale.
- Show 130402: has trend records, first date 2021-03-01, episodes 8-12 only, 49 of 50 scored. So AniList's records for it begin at episode 8: no episode 1-4 snapshots, hence no w1 features. A data gap, not a collector bug.

### The label_at_window_edge flag is mostly an artefact (found by me after the run)
0-request check of where the primary label sits relative to the finale day (schedule shows): offset 0 = 1,206, +1 = 82, -1 = 15, other 15. All 551 edge cases are "label = FIRST stored record" (536 at offset 0, 15 at offset -1); none is the last record. Stored snapshots are trimmed to start at the finale day, so a label on the finale day is the first record by construction. The flag as defined cannot tell a good label from a bad one. The meaningful signals: offset -1 (15 shows, label before the finale day) and offset > +1 (12 shows, label later than expected). I have NOT changed the flag; changing a definition after seeing the data is the instructor's call.

## Open questions for the instructor

1. Which single variant of the ep3-window rule is allowed? It is not implemented until named.
2. Request total for Model A: 77 + 155 + 839 + 503 = 1,574 (w2 alone: 503 of 800).
3. label_at_window_edge: redefine (e.g. flag only offset != 0 / last-record cases) or drop?
4. The 3 `no_records` and 5 shows with neither label: exclude from training as untrainable?
