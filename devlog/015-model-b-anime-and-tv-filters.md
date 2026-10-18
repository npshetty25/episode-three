# 015 — Model B show features from AniList + the TV-filter comparison (Phase 7, step 1)

- **Date:** 2026-10-19
- **Task:** TASK 015 from the instructor (spec v1.13 → v1.14). **121 AniList requests** (cap 160).
- **Status:** Done.

## Summary

Every anime Model B trains on (the Kaggle sample) or scores (Nirav's list) now has its show features from one source, AniList, in `model_b_anime`. A 0-request script measures how much the "MAL TV" and "AniList TV" definitions differ, so TASK 016 can apply one definition to both sides.

## Files changed (one commit each)

| Commit | What |
|---|---|
| `1402bbe` | `collect/model_b_anime.py`: universe, chunking, resumability plan, document mapping, unmapped records, queries (9 tests) |
| `07d022b` | `scripts/collect_model_b_anime.py` (`--dry-run`, `--force`, `--limit-chunks`, complexity fallback to 25, cap 160) |
| `5ad3ee6` | `features/tv_filters.py` (8 tests) and `scripts/compare_tv_filters.py` |

## Collection

- Universe 6,050 = Kaggle 4,593 + Nirav 4,593 − overlap 3,136. Plan 121 requests; actual 121 (1 trial + 120), 4.4 min, 0 × 429, 0 retries.
- Stored 5,897 documents (all with a usable drop_share), 154 unmapped MAL ids (401 sample rows, 0.05%). Database 28.5 MB of 512.
- 50 ids per request with `stats` caused no complexity error (the 25-per-request fallback was never used).
- One MAL id (32136, Narara Superboard, 1 sample row) maps to two AniList entries, hence 5,897 + 154 = 6,051. Both are stored.

## The filter comparison

| Definition | Rows | Anime | Users with 20+ rows | Drop rate |
|---|---:|---:|---:|---:|
| (i) MAL Type = TV (now) | 850,801 | 4,593 | 5,000 | 7.84% |
| (ii) AniList format = TV | 815,295 (95.8%) | 3,527 | 4,987 (13 below 20) | 7.72% |
| (iii) both | same as (ii) | | | |

MAL-TV anime by AniList format: TV 3,527 (76.8%), **TV_SHORT 873 (19.0%; 31,698 rows, 3.7%)**, no record 154, ONA 35, SPECIAL 3, OVA 1. Nirav under AniList TV: 4,181 labelled, 3.0% dropped; 11 are MAL non-TV, 864 too new for the 2020 file. AniList-TV but MAL-non-TV: only Nirav's 11 are identifiable; 10 of them have 60,478 completed/dropped rows from 48,019 users in the full file (109 M rows). Coverage: 100.0% of sample rows have an AniList record and a usable drop_share; of 262 MAL TV anime with unknown episodes, 162 fetched and 159 now have episodes (100 not in the universe, 2 requests).

## Recommendation for TASK 016

Re-filter the existing sample to AniList TV (0 extra requests): it keeps 95.8% of rows, 4,987 of 5,000 users (13 fall below 20 and must be re-checked), and the drop rate barely moves (7.84% to 7.72%). A redraw would add little (the AniList-TV/MAL-non-TV pool is about 0.3% of Nirav's list) and cost 259 more requests. The one real ruling is **TV_SHORT**: 873 anime (3.7% of rows) are MAL TV but AniList TV_SHORT; "AniList TV on both sides" removes them, and also removes Nirav's TV_SHORT entries (617 of his), which is consistent.

## Notes

1. `drop_share` and the raw status amounts are a snapshot of all users today, so using them as a feature for the same anime in training is a leak risk for the target (drop labels). That belongs to TASK 016 (recompute from training users only, as the data notes already say).
2. 53 stored documents have no AniList format; they are not TV.
