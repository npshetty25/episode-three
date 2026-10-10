# Nirav's profile vs the Model B training users

- **Generated:** 2026-10-10 13:57 UTC by `python scripts\profile_vs_training.py` (0 network requests; aggregates only, no titles)
- **Training users:** 5,000 (Kaggle MAL 2020 sample, seed 42; TV, non-adult, completed vs dropped, at least 20 such entries)
- **Nirav:** 12,735 entries on AniList; 12,220 completed or dropped across all formats (drop rate 1.7%)

## Result

Nirav's personal features use the **same filter as training**: TV format, non-adult, completed vs dropped (REPEATING counts as completed).

| Measure | Nirav | Training users (5,000) | Position |
|---|---|---|---|
| Labelled entries (TV, non-adult) | **4,181** | min 20, median 118, 90th pct 356, 99th pct 792, max 4,434 | percentile 99.98; 1 training user(s) with more |
| Dropped | 126 | n/a | n/a |
| Drop rate | **3.01%** | median 4.1%, mean 7.4%, max 70.7% | percentile 43.1; 2,845 training users higher |

- **Entry count:** Inside the training range (20 to 4,434), at the extreme end; only 1 of the training users has more, at percentile 99.98.
- **Drop rate:** Inside the training range (0.0% to 70.7%), at percentile 43.1 (training median 4.1%).

Same comparison with the training script's extra rule (episode count known and at least 2): 4,178 entries, drop rate 2.94% (percentiles 99.98 and 42.9).

## TV_SHORT: the comparison depends on how MAL types these shows

AniList marks 617 of Nirav's completed/dropped non-adult entries as `TV_SHORT` (episodes of 15 minutes or less). The task's filter (`format == TV`) excludes them. MAL has no such type, and the training data holds MAL type `TV`.

Using the Kaggle `anime.csv` (MAL's own types, 2020 snapshot) for the shows that exist there:

| TV_SHORT entries | Count |
|---|---|
| Typed `TV` by MAL | 493 |
| Typed otherwise by MAL {'ONA': 3, 'Special': 4} | 7 |
| Added to MAL after the 2020 snapshot (type unknown here) | 117 |
| No MAL ID | 0 |

So **almost all of the checkable TV_SHORT shows are `TV` on MAL**, and the training data would have counted them. Sensitivity:

| Counting | Labelled entries | Drop rate | Entry-count position |
|---|---|---|---|
| `format == TV` only (task filter) | 4,181 | 3.01% | percentile 99.98, inside |
| + TV_SHORT that MAL types as TV | 4,674 | 2.76% | percentile 100.00, OUTSIDE (above the training maximum) |
| + every TV_SHORT | 4,791 | 3.32% | percentile 100.00, OUTSIDE (above the training maximum) |

## Caveats to disclose in the Model Report

1. **His list is a bulk import.** The 12,735 entries were created in one minute from a MyAnimeList export. Statuses are roughly correct, but they are not a record of choices made on AniList, and progress and dates are mostly unset (these are never used as features).
2. **Format comparability.** The result above depends on how `TV_SHORT` is counted (see the sensitivity table). Counted the way MAL types them, his entry count is above everything the model saw in training.
3. **Only a few drops.** With 126 drops (TV only), his personal drop rate is a noisy estimate, so predictions for him lean mostly on show-level features.
4. **Extreme volume.** His entry count sits at, or just beyond, the very top of the training range, where the model has seen almost no similar users. The Model Report must say this next to any prediction shown for him.

## Conclusion

With the task's filter he is **inside** the training range, at its extreme top for entry count and typical for drop rate. Counted the way MAL types shows (including TV_SHORT), his entry count is **above the training maximum** (4,674 to 4,791 against 4,434), so the safe statement is that **his profile is at or beyond the edge of the training range for volume**. His drop rate is typical either way. His profile is usable as a demo with the disclosures above, and it is not evidence of model accuracy, which comes only from held-out test users.
