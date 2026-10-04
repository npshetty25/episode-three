# 002 — First Python ↔ Atlas connection, package skeleton, sample-data cleanup

- **Date:** 2026-10-04
- **Task:** TASK 002 from the instructor (spec v1.0)
- **Status:** Built and verified by the developer. **Waiting on Nirav's acceptance run**, including the actual `--yes` drop, which is left for him to run.

## Summary

Python now reaches Atlas: ping, storage report and a write/read/delete round trip all pass. The spec is saved as `docs/SPEC.md`, the skeleton from spec §10 exists, and both scripts work. The sample data has been measured (143 MB, 28% of the free tier) but not yet dropped.

## Files changed

| File | Change |
|---|---|
| `docs/SPEC.md` | Spec v1.0 saved verbatim |
| `episode_three/__init__.py`, `scripts/__init__.py` | Make both folders importable packages |
| `episode_three/config.py` | Loads `.env` by absolute path (works from any folder). `MONGODB_DB` defaults to `episode_three`. `get_mongodb_uri()` raises `ConfigError` with setup instructions if the URI is missing |
| `episode_three/db.py` | `get_client()` (one shared client; `serverSelectionTimeoutMS=10000`, `appname="episode-three"`), `get_db()`, `size_mb()` (dbStats `dataSize + indexSize`), `explain_error()` (friendly messages; strips the URI and password from all output) |
| `scripts/check_db.py` | Ping + server version, per-database storage vs 512 MB, timed write/read/delete round trip in `episode_three.healthcheck` (collection dropped afterwards) |
| `scripts/drop_sample_data.py` | Lists `sample_*` databases with sizes; dry run by default; `--yes` drops them; on a permission error, prints Data Explorer / Compass instructions |
| `.env.example` | `MONGODB_URI` and `MONGODB_DB` placeholders |
| `.gitignore` | Added `data/` and `artifacts/` |
| `app/`, `notebooks/`, `tests/`, `reports/` | Created, each with `.gitkeep` so Git tracks the empty folder |

## Verification (developer run)

| Check | Result |
|---|---|
| `python -m scripts.check_db` | `Ping OK (MongoDB server version 8.0.34)`; sizes printed; `Round trip OK (360 ms)`; exit 0 |
| `python -m scripts.drop_sample_data` (dry run) | Lists `sample_mflix 143.03 MB`; "nothing was dropped"; exit 0 |
| `.env` moved aside → `check_db` | Friendly "MONGODB_URI is missing" message, no traceback, exit 1. `.env` restored |
| Wrong password (env override, `.env` untouched) | "Authentication failed. Check the username/password…" Real password not in the output |
| `git check-ignore .env` | `.env` |

**Storage before the drop** (data + indexes, MB = 1024²):

| Database | Size |
|---|---|
| `sample_mflix` | 143.03 MB |
| `admin` | 0.00 MB |
| `local` | not readable by this user |
| **Total** | **143.03 MB of 512 MB (27.9%)** |

Only `sample_mflix` was loaded; there are no other `sample_*` databases. The Atlas dashboard showed 142.99 MB, which agrees with the script's figure.

**Other facts for the report:**
- **Database user role:** `atlasAdmin@admin`, read via the `connectionStatus` command. That role includes `dropDatabase`, so the script should be able to drop the sample data itself. To be confirmed by the `--yes` run.
- **Cluster region:** `AWS AP_SOUTH_1` (Mumbai), from node tags in the `hello` command. This resolves the unrecorded-region note in devlog 001.
- **Latency:** 5 consecutive pings took 139–760 ms (very variable, on Nirav's home network); the write+read+delete round trip took 360 ms. Bulk writes (`insert_many` / `bulk_write`, already in spec §5) will matter more than the 100 ops/sec cap.
- **Connection, TLS or allowlist problems:** none. It connected on the first try.

## Acceptance run by Nirav

*To be filled in from Nirav's output:* criteria 1–3 and 5, and the total after the drop.

## Failures and issues

- None during the build.
- Not done by the developer on purpose: `drop_sample_data --yes`. Spec §15 says Nirav runs the acceptance commands, and it's the one destructive step.

## Decisions

- **`get_mongodb_uri()` function instead of a module-level `MONGODB_URI` constant.** Importing `config` never crashes; the error appears only when the database is actually needed. Later tests can import the package without a `.env`.
- **`explain_error()` lives in `db.py`**, so every future script gets the same friendly messages. It also covers DNS/SRV lookup failures (spec risk 12 territory) and college-Wi-Fi port blocking, in addition to the three cases the task listed.
- **Secrets are stripped from every error message** (URI and password, raw and URL-decoded), after the leak recorded in devlog 001.
- **Sizes in MB = 1024² bytes**, which matches the Atlas dashboard.

## Questions and spec notes for the instructor

1. **`mal_user_lists._id` is numeric (`12345`),** which contradicts the §5 convention of "string `_id`s prefixed with their source". Suggest `"mal_user:12345"`, or note it as a deliberate exception.
2. **The `mal_user_lists` storage estimate looks about 35% low.** Each embedded entry repeats its field names in BSON. `{"anime_id": "mal:5114", "status": "completed", "episodes_watched": 64, "role": "history"}` is about 95 bytes, not 70. So 5,000 users × 200 entries ≈ 95 MB instead of 70 MB, and the project total ≈ 145 MB instead of 120 MB. That still fits, but it's worth re-checking with `dbStats` right after the Kaggle import, as risk 5 already says. The real average entries per user (filter: ≥20 completed/dropped) may also differ from 200.
3. Nothing else in the spec looked wrong for this task.

## Teach Nirav (covered in the chat)

1. Why secrets live in a git-ignored `.env`, and why `.env.example` is committed.
2. Client → database → collection → document, and why there is ONE shared `MongoClient`.
3. What counts toward the 512 MB (uncompressed data + indexes), and why the sample data goes before our imports.

## Next

- Nirav runs the acceptance commands; the developer fills in the section above and commits.
- Then TASK 003: AniList trend-data probe.
