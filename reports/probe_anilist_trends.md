# AniList score-trend probe (TASK 003)

- **Date:** 2026-10-04
- **Script:** `python -m scripts.probe_anilist_trends` (raw data in `data/probe/`, git-ignored; generated tables in `data/probe/summary.md`)
- **Recommendation: GO**, for the window **Fall 2018 → Summer 2026**: **90% (54/60)** of sampled shows in that window are usable. Details and proposed snapshot definitions are at the end.

## What was measured

**Sample.** 12 seasons (Fall 2016–Fall 2025, Spring 2026, Summer 2026). Per season, AniList's TV/ONA, Japan, non-adult anime with 8–30 planned episodes, sorted by popularity: the **top 3** and **ranks 31–33**. That gives 72 shows. Every season had at least 41 eligible shows, so no fallback ranks were needed.

**Per show:** every trend record with `releasing: true`, the airing schedule, and the current score from the season listing.

**Definitions used in the tables:**
- **Day:** a calendar day in **Japan time (JST)**. AniList stamps every trend record at 00:00 JST (e.g. `1695999600` = 2023-09-30 00:00 JST).
- **Score present:** `averageScore` is not null **and not 0**. AniList puts `0` on a show's first releasing day (41 records), not null.
- **Score on day before ep 4:** the record dated the JST day before episode 4's airing day has a score.
- **Usable finale:** the show is finished, its last releasing record is within −1…+7 days of the final episode's airing day, and that record has a score.
- **Usable:** score on day before ep 4 **and** usable finale. This is the GO criterion.

## Q1: Coverage, and is each show usable?

| Season | Shows | Any releasing records | Score on day before ep 4 | Score 7 days after ep 3 | Usable finale | **Usable** |
|---|---|---|---|---|---|---|
| Fall 2016 | 6 | 0% (0/6) | 0% | 0% | 0% | **0% (0/6)** |
| Fall 2017 | 6 | 83% (5/6) | 0% | 50% | 50% | **0% (0/6)** |
| Fall 2018 | 6 | 100% | 67% (4/6) | 67% | 83% | **67% (4/6)** |
| Fall 2019 | 6 | 100% | 100% | 100% | 83% | **83% (5/6)** |
| Fall 2020 | 6 | 100% | 100% | 100% | 100% | **100%** |
| Fall 2021 | 6 | 100% | 100% | 100% | 100% | **100%** |
| Fall 2022 | 6 | 100% | 100% | 100% | 100% | **100%** |
| Fall 2023 | 6 | 100% | 83% (5/6) | 83% | 100% | **83% (5/6)** |
| Fall 2024 | 6 | 100% | 100% | 100% | 100% | **100%** |
| Fall 2025 | 6 | 100% | 100% | 100% | 100% | **100%** |
| Spring 2026 | 6 | 100% | 67% (4/6) | 83% | 100% | **67% (4/6)** |
| Summer 2026 | 6 | 100% | 100% | 100% | 100% | **100%** |
| **Fall 2018 → Summer 2026** | 60 | 100% | 92% (55/60) | 93% (56/60) | 97% (58/60) | **90% (54/60)** |
| ↳ top 3 | 30 | | | | | 93% (28/30) |
| ↳ ranks 31–33 | 30 | | | | | 87% (26/30) |
| **All 72** | 72 | 90% (65/72) | 76% (55/72) | 82% (59/72) | 85% (61/72) | 75% (54/72) |

**Earliest usable season: Fall 2018.** Releasing records are **daily from 2018-03-20** onward. Before that, they exist only on episode days (about weekly) and carry **no popularity** (Fall 2017: 0% of records). Fall 2016 shows have **no releasing records at all**. Spring/Summer 2018 were not sampled, but they fall after the daily start.

**Why the 6 window shows failed:**

| Show | Reason |
|---|---|
| RErideD (Fall 2018) | Schedule starts at ep 5; no records around ep 1–4 |
| HERO MASK (Fall 2018) | Only 4 records, schedule has ep 1 of 15 (release pattern AniList didn't track) |
| Kandagawa JET GIRLS (Fall 2019) | Final episode delayed 2 weeks; releasing records stopped 7 days before it |
| Sousou no Frieren (Fall 2023) | Episodes 1–4 premiered together, so there is no "after ep 3, before ep 4" moment |
| Tongari Boushi no Atelier, Ganbare! Nakamura-kun!! (Spring 2026) | **AniList outage**: no records from about 2026-04-03 until 2026-04-20 (see Q2) |

## Q2: Record density

| Season | Median records | Range | Median % of 1-day steps | Largest gap (days) |
|---|---|---|---|---|
| Fall 2016 | 0 | 0–0 | n/a | n/a |
| Fall 2017 | 12 | 0–29 | 0% | 14 |
| Fall 2018 | 84 | 4–168 | 100% | 1 |
| Fall 2019 | 77 | 70–176 | 100% | 1 |
| Fall 2020 | 77 | 77–175 | 100% | 1 |
| Fall 2021 | 77 | 77–161 | 100% | 1 |
| Fall 2022 | 80.5 | 70–168 | 100% | 1 |
| Fall 2023 | 80.5 | 77–175 | 100% | 1 |
| Fall 2024 | 73 | 66–171 | 97% | 4 |
| Fall 2025 | 77.5 | 70–84 | 100% | 1 |
| Spring 2026 | 67 | 61–162 | 99.5% | 18 |
| Summer 2026 | 77 | 76–84 | 100% | 3 |
| **All** | **77** | 0–176 | **100%** | 18 |

- **Daily, one record per day, no duplicates.** A 12-episode show has 77–84 records: one per day from the day after ep 1 airs until the finale day.
- **AniList outages** (the same days are missing for every show that was airing then): **2024-11-21 and 2024-11-23 → 25**, **2026-04-03 → 04-19** (every Spring 2026 show's first releasing record is 2026-04-20), and **2026-07-07 → 08**.

## Q3: The `episode` field

| Group | Episode values compared with schedule | Within ±1 day | Offset (record day − airing day): count |
|---|---|---|---|
| All | 883 | **99%** | 0: 782, −1: 90, +7: 8, −7: 3 |

- **Yes, `episode` is non-null only on airing days.** All other days have `null`. In the probe window only 1 airing day had a record without its episode value.
- **The −1 offsets are all shows airing at exactly 00:00 JST** (Chainsaw Man, Komi-san, SAO Alicization, Mushoku Tensei, SHY…). For those, the episode value appears on **both** the day before and the airing day. This explains all the "11 repeated episode values" oddities.
- **+7 / −7** (11 values, 4 shows) are around broadcast breaks, where the schedule and the trend data disagree by a week.
- **Missing episodes inside a show's record range:** 4 shows, all caused by outages. Ao no Hako, Goukon ni Ittara… and Tsuma, Shougakusei ni Naru lost ep 9 to the Nov 2024 outage; Ganbare! Nakamura-kun!! lost eps 2–4 to the April 2026 outage.
- **Ep 1 markers are often absent:** releasing records usually **start the day after ep 1 airs**. Multi-episode premieres (Kusuriya eps 1–3, Frieren eps 1–4) leave no separate markers either.
- **Incomplete schedules:** 6 shows' schedules start after ep 1 (e.g. Slime 2018 has only ep 24; Re:Zero S3 starts at ep 10), and 1 short ONA has none. Of the 59 episode values more than a day from any airing, 56 come from these incomplete schedules; the other 3 are break-week shifts.

## Q4: `averageScore` availability

| Season | Median % of records with score | First score: days after ep 1 (median, range) | Score day before ep 4 | Score 7 days after ep 3 |
|---|---|---|---|---|
| Fall 2017 | 92% | 0 (0–7) | 0% | 50% |
| Fall 2018 | 99% | 2 (2–2) | 67% | 67% |
| Fall 2019 | 99% | 2 (1–3) | 100% | 100% |
| Fall 2020 | 98% | 2.5 (1–3) | 100% | 100% |
| Fall 2021 | 100% | 1 (1–2) | 100% | 100% |
| Fall 2022 | 100% | 1 (1–2) | 100% | 100% |
| Fall 2023 | 99.5% | 1 (1–2) | 83% | 83% |
| Fall 2024 | 99.5% | 2 (1–5) | 100% | 100% |
| Fall 2025 | 99.5% | 2 (1–2) | 100% | 100% |
| Spring 2026 | 100% | **15.5 (8–18)**, outage | 67% | 83% |
| Summer 2026 | 100% | 1.5 (1–2) | 100% | 100% |
| **All** | **99%** | **2 (0–18)** | **76% (55/72)** | **82% (59/72)** |

- Scores appear **1–2 days after ep 1**. The first releasing day is `0`, the next day has a real score.
- By ep 3, a score is present whenever a record exists. In the window, no show had a record on the day before ep 4 without a score. Every miss is a missing *record* (outage, premiere pattern).
- Early scores are jumpy: 5–10 point moves within the first week (BEASTARS 57 → 67 on day 3; Tonikaku Kawaii 63 → 72 on day 2). By ep 3 they are stable.

## Q5: The finale

| Group | Finished | Finale gap, days (median, range) | Finale score present | Median abs(finale − current) | Median abs(finale − score before ep 4) |
|---|---|---|---|---|---|
| Top 3 | 36 | 0 (0 to 1) | 100% (33/33) | 1 | 2 |
| Ranks 31–33 | 36 | 0 (−7 to 5) | 91% (29/32) | 2 | 2 |
| **All** | 72 | **0 (−7 to 5)** | **95% (62/65)** | **1.5** | **2** |

- The last releasing record sits **on the final episode's airing day** (median gap 0). It is the score at the moment the finale airs, before most reactions to it.
- Scores keep moving after the finale (Experiment 1): Mushoku Tensei Part 2 went 86 (finale day) → 87 (+7 days) → 87 (+30); One Punch Man 3 went 54 → 52 (+7) → 51 (+30) → 50 today.
- **Baseline preview (not an evaluation):** on the 54 usable shows, "finale = score before ep 4" (baseline B1) is off by **MAE 2.30 points** (RMSE 3.39; 78% within ±3; max 16). Scores **rise** on average (+0.93; 32 rise, 13 fall, 9 unchanged). That drift is learnable signal, and One Punch Man 3 (70 → 54) is exactly the case the model exists for.

## Q6: `popularity` and `inProgress`

| Group | Popularity, day before ep 4 | inProgress, day before ep 4 | Popularity, 7 days after ep 3 | inProgress, 7 days after ep 3 |
|---|---|---|---|---|
| Fall 2018 → Summer 2026 | 92% (55/60) | 92% (55/60) | 93% (56/60) | 93% (56/60) |
| All 72 | 76% (55/72) | 76% | 78% | 85% |

From 2018 onward, both are present on **100% of records** (median per show). Every miss is a missing record, the same misses as Q4. In 2017, `popularity` was never recorded and `inProgress` was.

## Q7: Request cost

- **The whole probe needs 249 requests:** 12 season listings + 225 for the 72 shows + 12 for experiments.
- **Requests per show:** median **3** (2 trend pages + 1 schedule), range 2–5. Mean of **78 trend records** per show.
- **First run:** 252 HTTP requests in **1,018 s (17 min)**. There were 2 × HTTP 429, each recovered by waiting 60 s, and 1 network error recovered after 5 s. Re-runs reuse saved data (the fixed-experiment re-run made 4 requests; the final re-run made 0).
- **Rate-limit headers:** every 200 response said `X-RateLimit-Limit: 30`, so the degraded limit *is* visible in headers. The lowest `X-RateLimit-Remaining` was 3. **Both 429s arrived while the header said 24 and 20 requests were remaining**, and the 429 answers carry no rate-limit headers. A second, hidden limiter exists, so watching `Remaining` cannot prevent 429s; honouring `Retry-After` is what works.

## Q8: Experiments

| Experiment | Result |
|---|---|
| `releasing: false` (3 shows) | Records exist **before airing** (from the announcement, e.g. One Punch Man 3 from 2022-08-18, with growing popularity) and **daily after the finale up to today** (Mushoku Tensei P2: 1,750 days). Post-finale records have scores (100% on the first 50 days for 2021 and 2025 shows). The 2016 show has daily not-releasing records but **no scores**. |
| `episode_lesser: 4` (SPY×FAMILY S2) | Returned **only the 2 records with episode 2 and 3**. Days with `episode: null` are excluded. |
| `mediaId_in` (3 shows) | **Works.** It returned all three shows' records (77, 77, 84, identical to individual queries), all three on the first page, in **5 requests instead of 6**. |
| Not planned: null filters | Passing a filter as `null` is **not ignored**: `mediaId_in: null` gives HTTP 500, and `episode_lesser: null` / `date_greater: null` give HTTP 400. |

**Do the tricks cut full-collection cost?** Estimates for about 1,000 shows:

| Plan | Requests | Time at 27/min (+ about 1 min of 429 wait per 125 requests) |
|---|---|---|
| A. Per show, as spec v1.1 §6 (2 trend pages + 1 schedule) + 62 listings | ~3,060 | ~1 h 55 m (+ ~25 m) |
| A + the finale+7 label proposed below (1 request per show) | ~4,060 | ~2 h 30 m (+ ~30 m) |
| **B. `mediaId_in` batches of ~10 shows:** full releasing curves (1,000 × 78 / 50 ≈ 1,560) + batched schedules (~260, *untested*) + finale-week label windows (~200) + listings | **~2,080** | **~1 h 17 m (+ ~15 m)** |
| C. Same as B, but only the date windows the model uses (start → ep 4, finale +7) | ~1,300 | ~50 m (+ ~10 m) |

- **`mediaId_in` cuts the cost roughly in half** compared with A plus the label. Merging shows removes half-empty last pages (2 pages per show becomes 1.56).
- **`episode_lesser` does not help.** It returns only airing-day records, and the snapshot we need (the day before ep 4) has `episode: null`.

## Surprises in the raw data

1. Records are stamped at **00:00 JST**, so day maths must use Japan time.
2. A show's **first releasing day has `averageScore: 0`**, not null.
3. **00:00 JST airings carry their episode number on two consecutive days.**
4. **Releasing records start the day after ep 1 airs.** Before that, records are `releasing: false`.
5. **Daily releasing data starts 2018-03-20.** 2017 is weekly with no popularity; 2016 has nothing.
6. **Outages:** about 17 days in April 2026, plus short ones in Nov 2024 and Jul 2026.
7. **Multi-episode premieres** (Frieren 1–4, Kusuriya 1–3) and **schedules that start mid-season** (Slime 2018, Re:Zero S3).
8. **Schedule and trend markers disagree by a week around breaks** (11 values).
9. A **24-episode ONA of 2-minute mini-dramas** (Chuunibyou "Take On Me Mini-Theater") passes the TV/ONA + 8–30 episode filter.
10. **`pageInfo.total` is a placeholder** (always 5000, `lastPage` 100). Only `hasNextPage` is reliable.
11. **429s happen with `Remaining` at 20+**, and **null filters crash queries** (Q7, Q8).

## Recommendation: **GO**

**Criterion met:** from **Fall 2018** onward, **90% (54/60)** of sampled shows have a score on the day before ep 4 **and** a usable finale record. That is above the 80% threshold. From Fall 2019 onward it is 93% (50/54). Top shows reach 93% and ranks 31–33 reach 87%. Shows below rank 33 were not sampled; the spec's popularity ≥ 2,000 filter limits that risk.

- **Season window:** **Fall 2018 → Summer 2026 = 32 seasons.** That is one season more than spec v1.1's Winter 2019 start. Spring and Summer 2018 fall after daily records began (2018-03-20) but weren't sampled; adding them would be a 12-request check. Nothing before 2018 is usable.
- **Estimated usable shows:** 32 seasons × 30–40 eligible (spec filter) × 0.85–0.90 ≈ **820–1,150, roughly 1,000**. Spring 2026 will lose shows whose ep 4 fell inside the April outage.
- **Risk to live predictions:** if an outage covers the days before a current show's ep 4, the Season Forecast page can't predict that show. It should say so rather than guess.

## Proposed exact definitions (for spec §7)

All days are JST calendar days. A record "has a score" when `averageScore > 0`.

1. **Episode marker day `M(n)`:** the earliest of (a) the JST day of episode n's `airingSchedule.airingAt` and (b) the day of the first trend record with `episode = n`. Taking the earliest keeps snapshots safely before any reaction to that episode, including the 00:00 JST double markers and break-week disagreements.
2. **ep 3 snapshot:** the latest releasing record dated within **[M(4) − 3, M(4) − 1]** that has a score. It requires **M(3) < M(4)**, which excludes premieres that release ep 4 together with ep 3, like Frieren. The 3-day window tolerates short outages. In the sample, the record exactly on M(4) − 1 existed for 92% of window shows. `popularity` and `inProgress` come from the same record.
3. **ep 1 snapshot:** the latest releasing record within **[M(2) − 3, M(2) − 1]** with a score. It requires **M(1) < M(2)**. Otherwise it is missing, with a `multi_episode_premiere` flag (Kusuriya keeps its ep 3 snapshot but has no ep 1 snapshot).
4. **Finale label:** `averageScore` of the record dated **M(final) + 7**, fetched with `releasing: false` and a date window. If that day is missing, use the nearest scored record within M(final) + 5…+9. `final` is the highest episode in the schedule. Store `label_source`.
   - **Why +7:** the last releasing record is the finale's *airing day* (median gap 0), before reactions to the finale. Scores keep moving afterwards (86 → 87, 54 → 52).
   - **Cheaper fallback:** use the last releasing record (95% scored, no extra request). Phase 6 should report results under both labels.
5. **Exclusions:** no ep 3 snapshot; no scored label; episode `duration` < 10 minutes (new filter, for shorts and mini-dramas; needs `duration` in the season listing).

## Proposed spec changes (v1.2)

- §6 season window → **Fall 2018 – Summer 2026**; add `duration ≥ 10`; collection via **`mediaId_in` batches** (plan B or C above).
- §7 snapshot and label definitions as above; Model A's split stays by time.
- §4.1 / client rules: **never send null filters**; rely on `hasNextPage` (`total` is fake); **429s come from a hidden limiter**, so honour `Retry-After` (already implemented) rather than steering by `X-RateLimit-Remaining` (risk 4).
- New convention: **JST days** for anything derived from trend dates; `averageScore == 0` means "no score".
- Optional v2 feature: **pre-airing popularity** (hype). `releasing: false` records exist from the announcement onward.

## Reproduce

```
python -m scripts.probe_anilist_trends
```
The first run takes about 17 minutes (about 250 requests). Later runs reuse `data/probe/` and finish in seconds. Generated tables are in `data/probe/summary.md`, and per-show numbers in `data/probe/analysis.json`.
