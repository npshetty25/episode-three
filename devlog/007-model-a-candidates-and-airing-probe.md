# 007 — Model A candidate list + airing-schedule probe (Phase 5, step 1)

- **Date:** 2026-10-17
- **Task:** TASK 007 from the instructor (new instructor chat, spec v1.5 → v1.6)
- **Status:** Done. All 7 acceptance checks passed on Nirav's machine (2026-10-17).

## Summary

- **Candidate list:** `model_a_candidates` holds every show AniList lists for Fall 2018 → Summer 2026 (32 seasons), with `eligible` and the reasons for every exclusion. It is resumable per season and capped at 100 requests.
- **Airing probe:** checks whether AniList's PAST airing schedules are complete enough to compute the marker days M(n). First live result (Fall 2018, 10 shows): 8 complete, 2 with gaps.
- **Spec v1.6** records the instructor's nine rulings. The "capped at 11,000" line in §4.1 was wrong: `my_entries` holds **12,735** entries.
- **Tests:** 67 offline tests pass (40 old + 27 new).

## Files changed (one commit each)

| Commit | Change |
|---|---|
| `e8bba2a` | `episode_three/collect/model_a_candidates.py` (`season_range`, `check_eligibility`, `to_candidate_doc`, `list_season`, `collect_season`, `summary_from_db`), `scripts/collect_model_a_candidates.py` (`--dry-run`, `--force`, `--test`), tests, hand-made fixture |
| `926ea3b` | `episode_three/collect/airing_probe.py` (`pick_probe_shows`, `summarize_show_schedule`, `season_verdict`), `scripts/probe_airing_schedules.py`, tests, `tests/fixtures/airing_schedules_sample.json` (one real, complete show) |
| `d846c7e` | `docs/SPEC.md` → **v1.6** |
| *(this)* | this devlog |

## Design

- **New collection, not `titles`:** the list sync never touches `model_a_candidates`, so it can be rebuilt freely. Indexes `(season_year, season)` and `eligible`.
- **Eligibility reason codes (pure function):** `format`, `country`, `adult`, `episodes_unknown`, `episodes_out_of_range` (not 8–30), `duration_unknown`, `duration_short` (< 10), `not_finished`. A show can have several. `popularity_ep3` comes later from trend data.
- **Pre-filter vs real filter:** the listing query uses CURRENT popularity ≥ 2,000 (`popularity_greater: 1999`) only to choose which shows to download. `current_popularity` and `current_average_score` are stored for analysis, never as features.
- **Resumable:** one `sync_runs` document per season (`_id` `model_a_candidates:<SEASON>:<year>`, job `model_a_candidates`), written LAST, so a crash mid-season is simply redone. Re-running skips finished seasons with 0 requests unless `--force`.
- **Request control:** Atlas is pinged before the first AniList request; `LISTING_REQUEST_CAP = 100` raises `RequestBudgetExceeded` before a request that would exceed it (the script stops, prints a summary, exits 2, and a re-run continues); a complexity error restarts the season at 25 per page (never triggered with 50 per page).
- **Dedupe:** by id within a season, since popularity can shift between pages.
- **Probe sample:** 10 eligible shows per season, EVENLY SPACED from most to least popular (not the top 10), deterministic. It needs the candidates collected first.

## Verification (developer)

| Check | Result |
|---|---|
| `python -m pytest -q` | **67 passed, 1 deselected**, network blocked |
| `collect_model_a_candidates --dry-run` | 32 seasons, `FALL 2018 ... SUMMER 2026`, "0 requests" |
| One real season into `episode_three_test` (Fall 2018) | listed **50**, eligible **40**; reasons `episodes_out_of_range` 9, `duration_short` 2; 2 requests; indexes `eligible_1`, `season_year_1_season_1`; done-marker recorded |
| `probe_airing_schedules --test` (Fall 2018 only in that DB) | 10 shows, 3 requests: **8 complete, 2 with gaps** (see below); the other two seasons correctly report "no candidates" |
| `my_entries` for npshetty25 | **12,735**, equal to the sync's number, and above the "11,000 cap" |
| Test database | dropped afterwards (rebuilt on demand) |

**Fall 2018 probe detail:** 8 shows have every episode in the schedule. One show (`episodes` 12) has only 8 rows and is missing episodes 1–4; one (`episodes` 13) has a single row (the finale only). So the schedule has the final episode for 10/10 but eps 1–4 for 8/10. That is why TASK 008 should not rely on schedules alone.

## Acceptance run by Nirav (PowerShell, 2026-10-17)

| # | Command | Result |
|---|---|---|
| 1 | `python -m pytest -q` | `67 passed, 1 deselected in 1.58s` ✅ |
| 2 | `collect_model_a_candidates --dry-run` | 32 seasons `FALL 2018 ... SUMMER 2026`, budget line, "0 requests" ✅ |
| 3 | `collect_model_a_candidates` | all 32 seasons; **1,665 listed, 1,431 eligible (86%)**; **55 requests** (cap 100), 0 × HTTP 429, 0 retries ✅ |
| 4 | same again | `32/32 seasons already collected, 0 requests` ✅ |
| 5 | `probe_airing_schedules` | 30 shows, **9 requests** (cap 15), 0 × 429; Fall 2018 8/10 complete, Winter 2022 9/10, Summer 2026 9/10 ✅ |
| 6 | `check_db` | `model_a_candidates` stored; `episode_three` **16.94 MB (3.3%)**, was 15.20 MB ✅ |
| 7 | `git log -5` | the four TASK 007 commits ✅ |

### Eligible per season (listed / eligible)

2018 FALL 50/40 · 2019 WINTER 38/34, SPRING 37/31, SUMMER 46/33, FALL 54/45 · 2020 WINTER 41/35, SPRING 47/38, SUMMER 24/18, FALL 45/37 · 2021 WINTER 55/46, SPRING 57/43, SUMMER 39/34, FALL 54/44 · 2022 WINTER 40/33, SPRING 56/43, SUMMER 52/43, FALL 53/44 · 2023 WINTER 61/53, SPRING 56/49, SUMMER 52/43, FALL 73/62 · 2024 WINTER 51/47, SPRING 60/55, SUMMER 52/51, FALL 62/56 · 2025 WINTER 51/47, SPRING 55/47, SUMMER 64/58, FALL 54/51 · 2026 WINTER 62/56, SPRING 63/60, SUMMER 61/55. **Total 1,665 / 1,431.**

### Exclusion reasons (a show can have several; percentages of 1,665 listed)

`episodes_out_of_range` 170 (10%) · `duration_short` 101 (6%) · `not_finished` 10 (1%) · `episodes_unknown` 5 · `duration_unknown` 2. No `format`, `country` or `adult` exclusions (the listing query already filters those).

**Why 1,431 is above the task's "roughly 800–1,400":** that range was an estimate of *usable* shows. 1,431 is only the candidate stage, before the "popularity ≥ 2,000 at episode 3" filter, before marker/snapshot exclusions and before the pending rule (finale + 9 days). TASK 003 measured about 90% of shows usable, so about 1,290 is a realistic final number. The count also rises over time (about 34 eligible per season in 2019, about 55 in 2025-26) because more shows pass today's popularity pre-filter.

### Airing-probe verdicts (30 shows; 26 complete, 4 with gaps, 0 missing)

| Season | Complete | Gaps | Eps 1–4 present | Final episode present |
|---|---|---|---|---|
| Fall 2018 | 8 | 2 | 8/10 | 10/10 |
| Winter 2022 | 9 | 1 | 9/10 | 9/10 |
| Summer 2026 | 9 | 1 | 9/10 | 10/10 |
| **All** | **26** | **4** | **26/30 (87%)** | **29/30 (97%)** |

The 4 gaps: one show with 8 of 12 rows (eps 1–4 missing), one with only its finale row, one with a single row (10 episodes, neither the early episodes nor the finale), and one with 11 of 12 rows (one early episode missing). Three of the four lack early episodes, which are exactly the ones M(3) and M(4) need.

## Findings worth knowing

1. **`hasNextPage` is true on a full page** even when nothing follows. Fall 2018 has exactly 50 qualifying shows, so page 2 came back empty. A season whose count is a multiple of 50 costs one extra request. The data is not truncated (page 1's last show had popularity 2,766).
2. **No complexity error** with `perPage: 50` and the relations selection.
3. **`airingSchedules(mediaId_in: …)` works** and batches shows (OPEN-3 resolved). 10 shows ≈ 105–120 rows ≈ 3 requests.
4. **The "capped at 11,000" line in spec §4.1 was wrong** for chunked requests: 12,735 entries came back. Fixed in v1.6.

## Failures and issues

1. **Atlas refused connections for several hours** (TLS `INTERNAL_ERROR`, IP changed). The fail-fast ping stopped every attempt before any AniList request. Nirav re-added his IP.
2. **A typo in my throwaway dev snippet** (`json.dump` argument) crashed it after the data was printed; the code itself was unaffected.
3. **The shell rejected a long inline Python script**, so the spec edit ran from a file instead. The script asserts every replacement matches exactly once.

## Decisions

- **`--test` flag on both scripts** (not in the task) so a developer check never touches production.
- **The probe script saves the fixture once and never overwrites it**, so Nirav's run leaves `git status` clean. The fixture is one real, complete show (13 rows).
- **The v1.4 changelog item order** was fixed (items 5 and 6 had been swapped).
- **Risks 12 and 15 merged** into 15.

## AniList requests

- **Developer: 13** (listing check 2, probe check 3, pagination debug 2, fixture 1, database test 2, probe script 3).
- **Nirav's run: 64** (listing 55 + probe 9). **Total 77 of the 120 hard cap.** No HTTP 429 and no retries in either run.

## Teach Nirav (covered in the chat)

1. Pre-filter vs real filter: current popularity decides what to download but is never a feature.
2. Exclusion reasons as data.
3. Request budgets and pagination.

## Next

- The instructor rules on the two questions below and sends TASK 008 (markers).
- **Recommendation for TASK 008:** use the airing schedule as the primary source of marker days and the trend episode markers as the fallback (M(n) is already defined as the earliest of the two). About 13% of probed schedules (4 of 30) lack early episodes, so shows missing both sources for episode 3 or 4 should be excluded with a recorded reason, not guessed.

## Questions for the instructor

1. With 4 of 30 sampled schedules lacking early episodes, should a show whose schedule lacks M(3) or M(4) be rescued from trend markers, or excluded?
2. hasNextPage is true on a full page: accept the occasional extra request, or stop when a page returns fewer rows than perPage?
