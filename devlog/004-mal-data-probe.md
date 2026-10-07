# 004 — Model B data probe (Kaggle MAL 2020) + spec v1.2

- **Date:** 2026-10-07 to 2026-10-08
- **Task:** TASK 004 from the instructor
- **Status:** Done. All 6 acceptance checks passed on Nirav's machine (2026-10-08). **Verdict: PARTIAL (mechanical)**, with a fix that leaves the sample untouched.

## Summary

Spec v1.2 records the instructor's TASK 003 rulings. The Kaggle MAL 2020 data is readable and matches the verified facts. 279,458 users qualify, and a reproducible 5,000-user sample (850,801 rows, 7.8% dropped) is saved to `data/processed/` (git-ignored).

Two problems keep the mechanical verdict at PARTIAL: 540 rows with undocumented status codes and 1 duplicate pair. Neither reaches the sample.

**Biggest finding:** the dataset ends in late 2020, so shows from 2023 onward have no `anime.csv` row. Model B's anime features at inference time must come from AniList.

Full report: `reports/probe_mal_data.md`.

## Files changed (one commit each)

| Commit | Change |
|---|---|
| `32e89b9` | `requirements.txt`: pandas 3.0.6, numpy 2.5.3, pyarrow 25.0.1, pytest 9.1.1 (+ dependencies); all support Python 3.13 |
| `2569c08` | `episode_three/config.py`: `get_mal_data_dir()` with friendly errors; `.env.example` gains `MAL_DATA_DIR` |
| `6807976` | `docs/data-notes/kaggle-mal-2020.md`: source, CC0 label + MAL/Jikan caveat, files, headers, status codes, eligibility, leakage notes |
| `2745bc6` | `scripts/probe_mal_data.py`: header/encoding/status checks, adult filter, two chunked passes, seed-42 sample, Parquet + ID list, verdict |
| `61aff7e` | `tests/test_probe_helpers.py`: the project's first pytest file (6 tests on tiny hand-made tables) |
| `1cb5d9e` | `docs/SPEC.md` → **v1.2** (all 11 rulings + §9 stack update) |
| `15d85f2` | `reports/probe_mal_data.md` |

## Verification (developer run, 2026-10-08)

| # | Acceptance check | Result |
|---|---|---|
| 1 | `git log --oneline -6` | Shows `TASK 004: spec v1.2` and `TASK 004: MAL data probe` ✅ |
| 2 | Find "v1.2" in `docs/SPEC.md` | Line 1 title, line 7 changelog entry ✅ |
| 3 | `python scripts\probe_mal_data.py` | Completed, `VERDICT: PARTIAL (unknown status codes [0, 5, 33, 55]; 1 duplicate pairs inside chunks)`, `Runtime: 137 s` (re-run 132 s) ✅ |
| 4 | `python -m pytest -q` | `6 passed` ✅ |
| 5 | `git status` / `git check-ignore -v` | Clean after commits; `.gitignore:6:data/  data/processed/mal_sample_5k_seed42.parquet` ✅ |
| 6 | Hash of `sample_user_ids_seed42.csv` | `56d37ec12b3dcfbad03f43531d23e727ca8a6c983a4b551217b8d1433fc3918f` on both runs ✅ |

### Acceptance run by Nirav (PowerShell, 2026-10-08)

| # | Result |
|---|---|
| 1 | `git log --oneline -6` lists `1cb5d9e TASK 004: spec v1.2` and `2745bc6 TASK 004: MAL data probe` ✅ |
| 2 | `Select-String "v1.2"` finds the title (line 1), the changelog (line 7) and the v1.2 sections ✅ |
| 3 | Probe completed: same numbers as the developer runs, `VERDICT: PARTIAL (...)`, `Runtime: 122 s` ✅ |
| 4 | `6 passed in 0.65s` ✅ |
| 5 | Working tree clean, up to date with `origin/master`; `.gitignore:6:data/  data\processed\mal_sample_5k_seed42.parquet` ✅ |
| 6 | SHA-256 before and after the re-run: `56D37EC12B3DCFBAD03F43531D23E727CA8A6C983A4B551217B8D1433FC3918F`, identical, and the same as the developer runs ✅ |

Japanese titles printed correctly in the VS Code terminal, which confirms `anime.csv` is fine and the earlier garbling was the console.

### Key numbers

| Measure | Value |
|---|---|
| Rows / users | 109,224,747 / 325,770 |
| Eligible anime | 4,734 TV (of 17,562) |
| Eligible users (≥ 20 labeled entries) | 279,458 |
| Sample | 5,000 users, 850,801 rows (784,126 completed, 66,675 dropped) |
| Drop rate | 7.8% (per user: median 4.1%; 23.6% never drop) |
| Entries per user | min 20, median 118, mean 170, max 4,434 |
| Distinct anime in sample | 4,593 |

### Status codes

1 Watching 5,228,658 · **2 Completed 68,089,751** · 3 On Hold 3,700,514 · **4 Dropped 4,266,591** · 6 Plan to Watch 27,938,693 · *undocumented:* 0 ×531, 5 ×6, 33 ×2, 55 ×1.

## Failures and issues

1. **The mechanical verdict is PARTIAL.** 540 rows (0.0005%) use codes 0, 5, 33 and 55, which are not in `watching_status.csv`, and there is 1 duplicate pair inside a chunk. Both are excluded from the sample (it keeps codes 2 and 4 only; 0 duplicates after `drop_duplicates`). *Proposed fix:* the Phase 7 importer drops undocumented codes and logs the count.
2. **The `pip install` took longer than the tool's 5-minute window** on a slow connection. It finished correctly in the background; no error.
3. **The task contradicts itself on the adult filter.** The context says exclude Hentai AND Rx; requirement 5 says not Hentai, not Rx. I implemented the stricter OR. The difference is 3 anime, none TV, so the data is unaffected. Question for the instructor.
4. **Optional step 13 asked for "10 recent anime from the TASK 003 fixtures"**, but the fixtures hold only one show. I used 10 Fall 2025–Spring 2026 shows from the TASK 003 probe sample instead (1 live request).
5. **Acceptance check 3 runs the script by path** (`python scripts\probe_mal_data.py`). That puts only `scripts/` on Python's import path, so the script adds the project root itself. `python -m scripts.probe_mal_data` also works.

## Decisions

- **Adult filter = OR** (stricter), see above.
- **Undocumented status codes** are reported and counted, not fatal. A mismatch in the code *table* itself would make the verdict PARTIAL and print a loud warning.
- **The sample keeps all 5 raw columns**, including `rating` and `watched_episodes`, for analysis. The report and data notes mark both as never-features for their own row.
- **The ID list is written sorted with `\n` line endings,** so its hash is stable across runs and machines.
- **The AniList → MAL check** used 1 request plus cached TASK 003 data (0 requests).

## Questions for the instructor

See `reports/probe_mal_data.md`. In short:
1. Accept PARTIAL with the fix?
2. Adult filter wording: AND or OR?
3. **Coverage gap:** anime from 2023 onward are absent from `anime.csv` (max MAL_ID 48,492; 0/10 recent shows). Use AniList features for both training and inference (fetch ~4,600 training anime via `idMal_in`, about 95 requests)?
4. The storage estimate drops to ~81 MB (170 entries/user, not 200).
5. Is excluding the 262 TV anime with unknown episode counts acceptable?

## Teach Nirav (covered in the chat)

1. Chunked reading: memory, `chunksize`, small dtypes.
2. Fixed seed + sorting = a reproducible sample.
3. Label leakage: `watched_episodes` / `rating` of the same row, and all-user drop counts.

## Next

- Instructor answers the questions; TASK 005 follows.
