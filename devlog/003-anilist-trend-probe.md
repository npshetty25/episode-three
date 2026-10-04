# 003 — AniList score-trend probe

- **Date:** 2026-10-04
- **Task:** TASK 003 from the instructor (spec v1.1)
- **Status:** Done and verified by the developer. **Recommendation: GO** (Fall 2018 → Summer 2026). Waiting on Nirav's acceptance run, which uses cached data and makes 0 requests.

## Summary

Spec updated to v1.1. Added a polite AniList client and a resumable probe that sampled 72 shows from 12 seasons. Daily trend data supports Model A from **Fall 2018** onward: **90% (54/60)** of sampled shows in that window have a score on the day before ep 4 and a usable finale record. The full report, with Q1–Q8, the recommendation and proposed snapshot/label definitions, is in `reports/probe_anilist_trends.md`.

## Files changed (one commit each)

| Commit | Change |
|---|---|
| `194630c` | `docs/SPEC.md` → v1.1 with changelog: prefixed `mal_user` ids, 95 B/entry storage estimate, constraints, standing rules (batching, timeouts, resumable jobs), small commits, Model A snapshots marked PENDING TASK 003 |
| `515e829` | `requirements.txt`: `requests==2.34.2` (+ its dependencies). Supports Python 3.13 per PyPI classifiers |
| `965c1de` | `episode_three/clients/anilist.py`: `post_query()` with ≥2.2 s spacing, 429 + `Retry-After` (default 60 s, max 5 waits), network/5xx retries at 5/15/45 s, 30 s timeout, error on GraphQL `errors`, rate-limit headers logged, running `stats` |
| `8b3df7d` | `scripts/probe_anilist_trends.py`: sampling, cached downloads under `data/probe/`, per-show analysis in JST days, 3 experiments, generated tables |
| `8135d1a` | `tests/fixtures/anilist_media_trends_page.json`, `anilist_airing_schedules_page.json` (SPY×FAMILY S2) |
| `1577d9d` | `reports/probe_anilist_trends.md` |

## Verification

| Acceptance criterion | Result |
|---|---|
| 1. Probe runs end to end, recovers from 429, prints a summary | ✅ First run: 252 requests, 1,018 s, 2 × HTTP 429 (waited 60 s each), 1 network error (retried after 5 s), exit 0. Re-runs: 4 requests, then 0 |
| 2. Report answers Q1–Q8 with tables, GO/PARTIAL/NO-GO, definitions | ✅ GO + definitions for M(n), ep 1 / ep 3 snapshots, finale +7 label, exclusions |
| 3. `data/probe/` git-ignored; 2 fixtures | ✅ `data/` is in `.gitignore` (git status never lists it); 2 fixture files committed |
| 4. Spec changelog + all 6 v1.1 changes | ✅ |
| 5. `requests` pinned | ✅ `requests==2.34.2` |

Client smoke test before the probe: season listing, trends, airing schedule, an invalid field (HTTP 400 raised without retry), and a null filter (HTTP 400 raised). The retry path was exercised for real by an HTTP 500 (see below).

## Failures and issues

1. **Trend query failed with HTTP 500 three times, then the client gave up (smoke test).** *Cause:* AniList does **not** ignore filters passed as `null`: `mediaId_in: null` crashes their server (500), and `episode_lesser: null` / `date_greater: null` give 400. *Fix:* every query names only the filters it uses; the rule is documented in `post_query`'s docstring. The client now also includes AniList's error message when retrying a 5xx. *Status:* resolved.
2. **2 × HTTP 429 during the probe** while `X-RateLimit-Remaining` still said 24 and 20. *Cause:* a hidden limiter beyond the per-minute header. *Fix:* none needed; `Retry-After` handling recovered automatically. *Note:* this contradicts the TASK 003 note that the degraded limit isn't in headers; `X-RateLimit-Limit: 30` was present on every 200 response.
3. **1 network `ConnectionError`.** Recovered on the first retry (5 s).
4. **Experiment bug: the 2016 `releasing: false` test was skipped.** *Cause:* shows with no trend records returned before their finale date was computed. *Fix:* schedule-derived fields are computed first. *Status:* resolved; re-run cost 3 requests.
5. **Experiment bug: the `episode_lesser` test was inconclusive** (0 records returned). *Cause:* the chosen show (Kusuriya) premiered eps 1–3 together and has no records with episode < 4. *Fix:* the candidate must have local records with episode < 4 (SPY×FAMILY S2). *Status:* resolved; 1 request.
6. **Three inaccuracies in my report draft**, caught by checking claims against `analysis.json` before committing: the cause of the "missing episodes" (outages, not late first records), 56 vs 57 incomplete-schedule values, and an empty table cell. Fixed before commit `1577d9d`.

## Decisions

- **Days are counted in JST.** Trend records are stamped at 00:00 JST; UTC days would misalign records and airings.
- **`averageScore == 0` counts as "no score".** It appears on each show's first releasing day.
- **`hasNextPage` only.** `pageInfo.total` is a placeholder (5000).
- **Show metadata comes from the season listing,** not a separate per-show request (saved 72 requests).
- **The probe is resumable:** each answer is saved before moving on (temp file + rename), so a crash never leaves half a file.
- **Logging:** every request goes to `data/probe/probe.log`; only warnings (retries, 429) go to the screen.
- **Two extra analyses added to the probe** so the report's numbers are reproducible from code: the daily-records start date and outage days, and post-finale score drift.

## Questions and spec notes for the instructor

1. Adopt the proposed **v1.2 changes** (report, last two sections): window Fall 2018 → Summer 2026, `duration ≥ 10` filter, the M(n)/snapshot/label definitions, JST days, the null-filter rule, and `mediaId_in` batched collection (plan B, or plan C for less data stored, in the spirit of AniList's no-hoarding rule)?
2. **Finale label:** finale + 7 days (proposed) vs. the last releasing record (cheaper). Phase 6 can report both; which is primary?
3. **Spring/Summer 2018:** spend 12 requests to check them, or start at Fall 2018?
4. **`Page.airingSchedules(mediaId_in: …)` is untested.** Plan B assumes it batches like `mediaTrends`. Verify in Phase 5, or skip schedules and rely on trend markers (99% within ±1 day)?
5. **Spec risk 4** ("read `X-RateLimit-Remaining` instead of hard-coding") should change: 429s arrive with Remaining at 20+, so `Retry-After` is the real protection.

## Teach Nirav (covered in the chat)

1. Probes/spikes, and why decision criteria are written down *before* seeing results.
2. GraphQL basics: one endpoint, exact fields, pagination with `page` / `perPage` / `hasNextPage`.
3. Being a polite API client: rate limits, 429 + `Retry-After`, backoff, and reading the terms of use.

## Next

- Nirav runs the acceptance command (cached, no requests).
- The instructor decides on v1.2 and sends TASK 004 (Kaggle dataset check).
