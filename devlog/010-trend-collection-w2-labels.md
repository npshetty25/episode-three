# 010 — Trend collection, window 2 (finale → finale + 10) and the labels (Phase 5, step 4)

- **Date:** 2026-10-19
- **Task:** TASK 010 from the instructor (spec v1.8 → v1.9)
- **Status:** Code, cap choice, flags and spec done; the full w2 run and its label counts are Nirav's acceptance run (numbers below marked "pending").

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

## Pending (Nirav's acceptance run)

Full w2 run: actual vs predicted records, requests, runtime, 429s; `check_labels` counts (primary / secondary found, flag counts with example ids, fallback shows separately); verdict on show 130402 from `probe_trends_single`.

## Open questions for the instructor

1. Which single variant of the ep3-window rule is allowed? It is not implemented until named.
2. Request total for Model A: 77 + 155 + 839 + 1 = 1,072 so far, plus Nirav's w2 run (about 548 predicted).
