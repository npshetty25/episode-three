# 005 — AniList list sync into MongoDB (Phase 3) + spec v1.3

- **Date:** 2026-10-08
- **Task:** TASK 005 from the instructor
- **Status:** Done. Acceptance checks 1–3, 5 and 6 passed on Nirav's machine (2026-10-08). Check 4 synced 139 entries into `episode_three`; the profile-page comparison is awaiting Nirav's confirmation.

## Summary

Spec v1.3 records the TASK 004 rulings and the tracker decision: AniList is the tracker, and this app is a read-only dashboard on top of it (clause 5). A read-only sync now copies Nirav's public AniList list (139 entries) into `titles`, `my_entries` and `sync_runs`.

The sync is idempotent: a second run reports **0 inserted, 0 modified, 0 deleted**. It deletes entries that disappear from AniList. The project now has its first real offline test suite: **25 tests, with the network blocked**, plus 1 live test.

## Files changed (one commit each)

| Commit | Change |
|---|---|
| `06d3b14` | `config.get_anilist_username()`; `.env.example` gains `ANILIST_USERNAME` |
| `2ec9b2b` | `db.get_client(tz_aware=True)`: dates read from Atlas carry UTC, so they equal freshly built ones (needed for change detection) |
| `c37b88e` | `scripts/check_db.py` runs by file path (acceptance check 5 uses `python scripts\check_db.py`) |
| `c09e44b` | `episode_three/anilist_sync.py`: `fetch_list`, `unique_entries`, `to_entry_doc`, `to_title_doc`, `plan_changes`, `write_changes`, `sync`, `stale_entries`, `count_without_dates`, `MAL_IMPORT_CUTOFF` |
| `ad0d27a` | `scripts/sync_anilist.py` (`--test`, `--stale`, `--username`); creates indexes on `title_id` and `mal_status_code` |
| `7b41945` | `pytest.ini` (`live` marker, default `-m "not live"`), `tests/conftest.py` (autouse network block) |
| `3d67dfc` | Fixtures: hand-made 7-entry list (all 6 statuses incl. REPEATING, unscored, partial dates, custom-list duplicate), empty list, real unknown-user answer |
| `a7e0817` | `tests/test_anilist_sync.py` (12), `tests/test_anilist_client.py` (6), `tests/test_live_sync.py` (1 live) |
| `7cdb14b` | `docs/SPEC.md` → **v1.3** |

## Verification (developer)

| Check | Result |
|---|---|
| `python -m pytest -q` | `25 passed, 1 deselected` (offline; the guard blocks sockets, DNS and `create_connection`) |
| `python -m pytest -m live -q` | `1 passed, 25 deselected`: one fetch, two syncs, second run 0 inserted / 0 modified / 0 deleted / 139 unchanged |
| `python scripts\sync_anilist.py --test` (first run) | fetched 139, **inserted 139**, modified 0, deleted 0; titles 139 inserted; 1 request |
| `sync_runs` | One document per run; the last run shows `inserted 0, modified 0, unchanged 139` |
| Indexes | `_id_`, `title_id_1`, `mal_status_code_1` |
| `python scripts\check_db.py` | **Before: 0.00 MB.** After the test sync: `episode_three_test` 0.24 MB |

### Acceptance run by Nirav (PowerShell, 2026-10-08)

| # | Command | Result |
|---|---|---|
| 1 | `python -m pytest -q` | `25 passed, 1 deselected in 1.56s` ✅ |
| 2 | `python -m pytest -m live -q` | `1 passed, 25 deselected in 80.62s` ✅ |
| 3 | `sync_anilist.py --test` ×2 | Run 1: entries inserted 0 / modified 0 / unchanged 139 / deleted 0; titles modified 1 (a score/popularity change on AniList since the developer's run). Run 2: **entries 0/0/139/0 and titles 0 modified** ✅ |
| 4 | `sync_anilist.py` | `episode_three`: **inserted 139**; COMPLETED 73, CURRENT 13, DROPPED 3, PAUSED 1, PLANNING 49. Comparison with anilist.co/user/npshetty25: awaiting confirmation |
| 5 | `check_db.py` | Before 0.00 MB → after: `episode_three` 0.19 MB, `episode_three_test` 0.29 MB, **total 0.48 MB (0.1%)** ✅ |
| 6 | `git status` / `git log -10` | Clean, up to date; `7cdb14b TASK 005: spec v1.3` and all 9 sync commits listed ✅ |

**Total AniList requests for the task: 9** (developer 5 + Nirav 4) of the 10 budgeted.

### Counts by status (AniList, 2026-10-08)

| Status | Entries |
|---|---|
| COMPLETED | 73 |
| CURRENT | 13 |
| DROPPED | 3 |
| PAUSED | 1 |
| PLANNING | 49 |
| **Total** | **139** |

There are no REPEATING entries, no custom lists, and no private or hidden entries. 136 of 139 are unscored, and 138 of 139 have no start or finish date.

### Origin-rule evidence

- **All 139 entries have the same `createdAt`: 1791449874 = 2026-10-08 08:57:54 UTC, to the second.** That's the MAL import.
- Only 2 entries were updated afterwards (One Piece at 09:00:21, My Hero Academia 7 at 09:00:45): Nirav's own edits.
- **Rule:** created before `MAL_IMPORT_CUTOFF = 2026-10-08 10:00 UTC` → `"mal_import"`; otherwise `"anilist"`. A missing `createdAt` counts as imported. Result: 139 × `mal_import`.

### Unknown user and empty list

- **Unknown username (real answer):** HTTP **404**, `{"errors": [{"message": "User not found", "status": 404, ...}], "data": {"MediaListCollection": null}}`. Saved as `tests/fixtures/anilist_unknown_user_response.json`. `fetch_list` turns it into: *"AniList has no user named '…'. Check ANILIST_USERNAME in .env …"*. The client raises without retrying, because a 4xx answer with GraphQL errors isn't retried.
- **Empty list:** tested with a hand-made fixture (`lists: []`). The sync records 0 entries and still writes a `sync_runs` document. Not verified live, since that would need an account with an empty list.

### `statusDistribution` findings (not stored)

- **Shape:** `stats { statusDistribution { status amount } }` returns 5 items: CURRENT, PLANNING, COMPLETED, DROPPED, PAUSED. Example, *86: Eighty Six*: COMPLETED 192,694, DROPPED 8,088, PAUSED 8,681, CURRENT 24,430, PLANNING 93,947.
- **Via `Page.media(id_in: […], perPage: 50)`:** works (3 titles, 1 request).
- **Inside `MediaListCollection`:** also works, with **no complexity error**, on the full 139-entry list (it was included in exploration request 1).

### Requests used: 5 logical AniList requests by the developer (budget 10)

1. List + `statusDistribution` inside `MediaListCollection` (exploration; raw answer saved to `data/probe/anilist_list_raw.json`, git-ignored)
2. Unknown-user answer
3. `statusDistribution` via `Page.media` (3 network `ConnectionError`s first, recovered by the 5/15/45 s retries; those attempts never reached AniList)
4. `sync_anilist.py --test`
5. Live test (1 fetch, 2 syncs)

Nirav's acceptance runs add 4 (`--test` ×2, live test, real sync), for **9 in total**.

## Failures and issues

1. **Atlas refused one connection** (`SSL handshake failed … TLSV1_ALERT_INTERNAL_ERROR`). This is what Atlas does for an IP not on the access list. `check_db`'s message correctly said to check Network Access. A retry minutes later worked, either because the network or IP changed back or because Nirav updated the list.
2. **3 network `ConnectionError`s** on request 3. Recovered automatically on the 4th attempt.
3. **A wrong timestamp in my hand-made fixture** (1791457074, which is 10:57:54 UTC, after the cutoff). The origin-rule test caught it; I corrected it to the real 1791449874.

## Decisions

- **Change detection before writing.** `plan_changes` compares fresh documents with stored ones (ignoring `synced_at`) and writes only new or changed ones. That's what makes a re-run report 0 modified; a blind `$set` would rewrite `synced_at` every time. `synced_at` therefore means "last time this document's content changed".
- **Every entry carries `username`**, and deletion is scoped to it, so `--username someone` can never delete Nirav's entries.
- **Titles are never deleted** (no personal data; other features may need them). Their `current_*` score and popularity change on AniList daily, so titles can legitimately show "modified" on a re-sync.
- **`--stale` reads from the database only**, so it uses 0 requests.
- **The live test fetches once and syncs twice,** to protect the request budget. The script run proves the two-fetch case.
- **No mongomock** (new dependency). The diff logic is tested as pure functions, and the real Mongo round trip is the live test.

## Questions for the instructor

1. **`origin` is all `mal_import` (139/139)**, because the list was created by the import today. Model B's personal history therefore starts as "imported". Should the dashboard show a banner until Nirav has reviewed the 14 stale entries?
2. **136/139 entries are unscored.** Model B doesn't use scores, but the dashboard's "my score" column will be mostly empty. Fine for v1?
3. **`statusDistribution` works inside `MediaListCollection`.** Should Phase 7/8 fetch drop shares for Nirav's own titles in the same sync request (0 extra requests), or keep stats out of the sync as now?
4. **`hiddenFromStatusLists` and `private` are fetched but not stored.** Both are 0 for Nirav; confirm they aren't needed.

## Follow-up (2026-10-09): stale-report rule changed (deviation from the task text)

- **Problem:** the task said to list CURRENT/PAUSED entries that are `origin = "mal_import"` OR older than 180 days. `origin` never changes, so after Nirav fixes the 14 entries on AniList, `--stale` would still list all 14.
- **Change (Nirav approved):** an imported entry is listed only while it is untouched, meaning `updated_at` is within `IMPORT_EDIT_GRACE_SECONDS = 60` of `created_at`. The 180-day rule is unchanged.
- **Effect on current data:** One Piece was edited about 2.5 minutes after the import (`updated_at` 09:00:21 vs `created_at` 08:57:54), so the report should now show **13** entries, not 14 (not yet confirmed against the database; a DNS timeout interrupted my check).
- 26 offline tests pass (1 new). Commits: code + script, then test.
- **Phase 4 decision (Nirav):** own TV/movie tracker with TMDB.
- **Check 4 (profile counts vs AniList)** is still waiting for Nirav to look at his profile page.

## Teach Nirav (covered in the chat)

1. Upsert and idempotency: why a second sync changes nothing, and how fixed `_id`s make that possible.
2. Why normal tests never touch the network, and what a fixture is.
3. Source of truth: AniList's clause 5, and why this app reads the list instead of becoming a tracker.

## Next

- Nirav confirms by_status matches anilist.co/user/npshetty25.
- Nirav fixes the 14 stale Watching/Paused entries on AniList himself (`--stale` lists them).
