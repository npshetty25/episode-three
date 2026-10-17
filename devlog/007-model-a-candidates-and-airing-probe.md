# 007 — Model A candidate list + airing-schedule probe (Phase 5, step 1)

- **Date:** 2026-10-17
- **Task:** TASK 007 from the instructor (new instructor chat, spec v1.5 → v1.6)
- **Status:** Built and verified by the developer on one season in the test database. **Waiting on Nirav's acceptance run** (the full 32-season collection and the 30-show probe). The real per-season counts and probe verdicts come from that run.

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
- **Expected for Nirav's run:** about 64 (32 seasons × 2) + about 9 = ~73, so ~86 in total against the hard cap of 120. If the listing needs more pages, the collector stops itself at 100.

## Teach Nirav (covered in the chat)

1. Pre-filter vs real filter: current popularity decides what to download but is never a feature.
2. Exclusion reasons as data.
3. Request budgets and pagination.

## Next

- Nirav runs the acceptance commands and pastes the output; the real numbers are then added here.
- Recommendation for TASK 008 comes after that run.
