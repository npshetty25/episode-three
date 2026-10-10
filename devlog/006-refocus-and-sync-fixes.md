# 006 (revised) — Project refocus (spec v1.5), sync improvements, profile check

- **Date:** 2026-10-10
- **Task:** TASK 006 (revised) from the instructor. Parts B/D/E of the earlier TASK 006 (TV/movie tracker) are cancelled.
- **Status:** Built and verified by the developer. Waiting on Nirav's acceptance run (including the one forced sync, 26 AniList requests).
- **Earlier devlog kept as is:** `006-tv-movie-tracker.md` (terms check, Part C migration, re-import).

## Summary

- **Spec v1.5:** the project is now a portfolio piece. Phases 4 (TV/movie), 10 (music) and 11 (TV Model A) are marked REMOVED with reasons (numbers kept). The rejected alternatives are collected in a new §17.
- **Three sync improvements:** origin by burst detection, an Atlas ping before any AniList request, and skipping a sync that is under 24 hours old (`--force` overrides).
- **Profile check (0 requests):** with the task's filter Nirav sits **inside** the training range at its extreme top. But counted the way MAL types shows, he is **above** it (see the finding below).
- **Tests:** 40 offline tests pass (was 29), 1 live test.

## Files changed (one commit each)

| Commit | Change |
|---|---|
| `d4365fe` | `docs/SPEC.md` → **v1.5** (11 changelog items, REMOVED markers, §8 demo profiles, §17 rejected alternatives) |
| `a13c308` | **Burst-detection origin.** `import_burst_minutes`, `entry_origin(created_at, burst_minutes)`, `build_entry_docs`; `MAL_IMPORT_CUTOFF` removed; `IMPORT_BURST_MIN_ENTRIES = 50`. Tests: burst of 60 + 3 singles, burst of 49 (not an import) vs 50, two bursts, missing `createdAt` |
| `76bb3fd` | **Fail fast.** `ping_database`; `sync(..., ping=, fetch=)` pings before any AniList request; the script pings first and prints "AniList requests used: N" on failure. Tests with injected functions |
| `51fcd34` | **Skip if recent.** `SYNC_MIN_INTERVAL_HOURS = 24`, `last_sync_finished_at`, pure `should_skip_sync`, `--force`. Test of the decision (3.5 h, exactly 24 h, 72 h, custom interval, never synced) |
| `be48f93` | `scripts/profile_vs_training.py` + `tests/test_profile_vs_training.py` (4 tests) |
| `4310100` | `reports/profile_vs_training.md` (aggregates only) |
| `2b8d29f` | Spec v1.5 correction: records the TV_SHORT finding |
| *(next)* | Origin counts printed after a sync; this devlog |

## Verification (developer; 0 AniList requests)

| Check | Result |
|---|---|
| `python -m pytest -q` | `40 passed, 1 deselected` |
| `python scripts\sync_anilist.py` (last sync 0.3 h old) | `synced 0.3 h ago, use --force (syncs under 24 h apart are skipped)`, `AniList requests used: 0` |
| Burst rule against the stored data | 12,735 entries, all created in **one UTC minute**; the rule labels all 12,735 `mal_import`; **0 stored origins would change** |
| `python scripts\profile_vs_training.py` | prints the comparison; writes `reports/profile_vs_training.md` |
| `Select-String "v1.5" docs\SPEC.md` | title, changelog entry and 28 other lines |

**Not run by the developer: the forced sync (26 requests).** The task's budget is 30 and one forced sync costs 26, so I left it for Nirav's acceptance run. The burst-rule check above shows what its origin counts will be.

## Profile comparison (training users: 5,000; entries min 20, median 118, 99th pct 792, max 4,434)

| Counting | Labelled entries | Dropped | Drop rate | Entry-count position | Drop-rate position |
|---|---|---|---|---|---|
| All formats, adult included | 12,220 | 203 | 1.7% | not comparable | n/a |
| **Task filter: format TV, non-adult** | **4,181** | 126 | **3.01%** | percentile 99.98 (1 training user has more): **inside, at the extreme top** | percentile 43.1 (training median 4.1%): **inside, typical** |
| + the training script's rule (episodes ≥ 2) | 4,178 | n/a | 2.94% | percentile 99.98 | percentile 42.9 |
| + TV_SHORT that MAL types as TV (493) | 4,674 | n/a | 2.76% | **above the training maximum** | n/a |
| + every TV_SHORT (617) | 4,791 | n/a | 3.32% | **above the training maximum** | n/a |

**TV_SHORT answer (the task asked whether MAL's "TV" includes some):** yes, almost all. Of the 617 non-adult labelled `TV_SHORT` entries, 493 are typed `TV` by MAL in the 2020 snapshot, 7 `ONA`/`Special`, and 117 were added to MAL after the snapshot (type unknown).

**Two corrections to the task's premise:**
1. The 12,220 labelled entries and 1.7% drop rate are across **all formats, adult included**. With the training filter, it is 4,181 entries and 3.0%.
2. With that filter he is **inside** the training range (the maximum is 4,434), not outside; only 1 of 5,000 users has more. He goes **outside** only if TV_SHORT is counted as MAL counts it. The spec and the report state both.

## Failures and issues

1. **First attempt's stale test:** an old test asserted the removed `MAL_IMPORT_CUTOFF`; replaced by the burst tests (a13c308).
2. **Report wording glitches** in my first output ("1 users have more", "43.1th percentile"); fixed before committing.
3. **No live failures.** No Atlas refusals this session.

## Decisions

- **`to_entry_doc` takes `origin` as an argument.** Burst detection needs the whole list, so `build_entry_docs` computes the burst minutes once and passes each entry's origin in.
- **The burst window is the UTC minute, as specified.** A real import that straddles a minute boundary could split into two groups below 50 each and be missed. The 12,735-entry import was entirely in one minute. See question 1.
- **The test uses a lower threshold (4)** for the 7-entry fixture, and separate tests use the real threshold of 50.
- **The profile script reads `anime.csv`** (only to type TV_SHORT shows by MAL's own classification). That's local data, still 0 network requests.
- **The report holds aggregates only.** No titles are written to it.
- **I did not spend 26 requests on a developer-side forced sync** (budget 30).

## AniList requests used

- **Developer: 0.** Everything ran against the database, the Kaggle sample and a skipped sync.
- **Nirav's acceptance run:** 26 (the forced sync). Total 26 of 30.

## Questions for the instructor

1. **Burst boundary:** a burst of 60 spread across 12:59:50–13:00:10 would split into 30 + 30 and be classed as "anilist". Use a sliding window (any 60-second span with ≥ 50 entries), or accept the minute rule?
2. **TV_SHORT:** should Model B's personal features use "TV + TV_SHORT-typed-as-TV-on-MAL" (4,674 entries, above the training range), or the task filter (4,181)? The first matches how the training data was typed; the second stays within the range. Either way the report discloses both.
3. **Dashboard demo for Nirav:** since his profile is at or beyond the edge for volume, should the "Will It Be Dropped?" page show his predictions with a visible warning banner, or only the held-out Kaggle test users?
4. **Dropped entries in his own profile are few** (126 TV): is a personal drop rate this noisy worth showing at all, or should the page lean on show-level features for him?

## Teach Nirav (covered in the chat)

1. Out-of-distribution: why a model trained on users with up to ~4,400 entries can't be trusted for a profile with more, and how we disclose it honestly.
2. Fail fast: why checking the database before spending API requests is good design.
3. Why cutting features made the portfolio stronger.

## Next

- Nirav runs the acceptance checks and pastes the output.
- The instructor rules on questions 1–4 and sends the next task (Phase 5: Model A data).
