# 006 — TV & movie tracker with TMDB (Phase 4)

- **Date:** 2026-10-09
- **Task:** TASK 006 from the instructor
- **Status:** **STOPPED at Part B (terms check)**, before any code, as the task instructs. Three blockers need decisions; no feature work was done.

## Summary

The terms check found a material clause that TASK 006's context doesn't mention. The current TMDB terms restrict using TMDB content **for, or in connection with, machine-learning / AI applications**, and they explicitly restrict **training or validating ML systems** on TMDB content.

- **Phase 11** (an experimental TV Model A trained on TMDB episode ratings) falls under that restriction.
- **The Phase 4 tracker** (TMDB metadata shown only for display) is *not clearly* forbidden. But "in connection with … an ML-based Application" is ambiguous, because Episode Three is an ML app.

Two practical blockers come on top: there is no TMDB token in `.env`, and Nirav's ISP blocks TMDB at the DNS level.

## Part B: terms-check findings

### I could not read the official pages word for word

| Attempt | Result |
|---|---|
| Fetch `www.themoviedb.org/api-terms-of-use` and `/terms-of-use` | Nirav's network resolves `www.themoviedb.org` **and `api.themoviedb.org`** to **49.44.79.236**, a block address on his ISP (Jio). The connection is refused. |
| Real addresses via Google DNS-over-HTTPS (`www` → 18.161.229.x CloudFront, `api` → 108.157.4.51) | `api`: a real TMDB answer (`{"status_code":7,"status_message":"Invalid API key…"}` without a token), so **the block is DNS-only**. `www`: **HTTP 403 "Just a moment..."**, a CloudFront bot challenge that only a real browser passes. |
| Internet Archive copies | WebFetch may not read archive.org; direct download got HTTP 429 (rate-limited) |
| Web search (runs outside Nirav's network) | Worked, but returns **search-engine extracts of the official pages, not verified verbatim text** |

### Clauses found (search extracts; the instructor should confirm against the live pages)

1. **Caching:** you must not *"cache, for longer than 6 months, any information obtained through or from TMDB or the TMDB APIs"*. This matches the task context.
2. **Attribution:** the TMDB logo plus a notice in an "About" or "Credits" section, with the logo *"less prominent than the logo or mark that primarily describes the application"* and not implying endorsement.
   - **The notice wording differs between sources.** Older, widely quoted: *"This product uses the TMDB API but is not endorsed or certified by TMDB."* The task context: *"This [website, program, service, application, product] uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise approved by TMDB."* The current wording needs confirming.
3. **Non-commercial:** the service is *"made available only for personal, non-commercial use"* unless expressly authorised in writing.
4. **Other restrictions:** no *"cloak[ing] or conceal[ing]"* the identity of the application; no application that *"uses excessive bandwidth, degrades access to TMDB, or adversely impacts the stability of TMDB's systems"*.
5. **ML/AI, new and not in the task context:**
   - **API terms (reserved rights):** TMDB *"reserves all rights not expressly granted herein, including the right to make derivatives of the TMDB APIs or TMDB Content, or to use the TMDB APIs or TMDB Content in connection with, or for training, a machine learning or artificial intelligence based Application."* One search extract phrases this as a prohibition on using *"the TMDB APIs or TMDB Content in connection with, including for training, a machine learning (ML) or artificial intelligence (AI) based Application."*
   - **Site terms:** users must not *"train or validate a machine learning or artificial intelligence system (including large language models and Chatbots) using … the Materials, collect data sets containing … the Materials for such training or validation, or provide archived or cached data sets containing … the Materials"* to others.
6. **Staff clarification (forum, not a contract term):** in the TMDB Talk thread "Clarification needed — 'training an AI/ML system'" (July 2026, `themoviedb.org/talk/6a5e284be6125cf4396873a6`), a TMDB staff member reportedly said a **personal, non-commercial portfolio recommendation feature** does not count as the restricted use, provided TMDB is attributed.
7. **Public GitHub project:** no clause found about publishing *code*. But committing real TMDB responses (for example as test fixtures) would keep TMDB data beyond 6 months and redistribute it. So fixtures must be **hand-made**, as the task already plans.

### What this means for our design

| Part of the plan | Assessment |
|---|---|
| Phase 4 tracker (TMDB metadata for display only) | **Not clearly forbidden**, but ambiguous under "in connection with … an ML-based Application". Proposed mitigation: a hard rule that **TMDB data never enters any model, feature, training or validation set**; models read only AniList/Kaggle-derived data; TMDB titles stay clearly separated; credits on the About page. |
| Model B inference | Must **exclude manual TV/movie entries** (they would bring TMDB genres and other fields into model features). |
| Phase 11 experimental TV Model A on TMDB episode ratings | **Restricted** (training/validating on TMDB content). Recommend removing it from scope, or finding a different data source. |

## Other blockers

1. **No `TMDB_API_READ_TOKEN` in `.env`.** Only `MONGODB_URI`, `MAL_DATA_DIR` and `ANILIST_USERNAME` are present. Nirav needs a TMDB account and an API Read Access Token.
2. **DNS block on Nirav's network.** `api.themoviedb.org` resolves to the block address; plain lookups via 8.8.8.8 also returned nothing, which suggests interception. The fix belongs on the machine: **Windows 11 encrypted DNS (DNS over HTTPS)**. Pinning IP addresses in code was rejected: brittle, and it would hide the problem.

## Requests used

- TMDB: **1** unauthenticated request to `api.themoviedb.org/3/configuration`, to prove reachability at the real address (budget 30).
- `www.themoviedb.org`: 2 page fetches (HTTP 403 bot challenge).
- AniList: 0.

## Files changed

- This devlog only. No code, as required by "Part B FIRST" and "STOP and report".

## Decisions

- **Stopped instead of building:** the verbatim terms could not be read, and a material ML/AI clause the instructor didn't list may cover the project. The ruling belongs to the instructor.
- **Part C (AniList deletion scoping + `synced_at` → `content_changed_at`)** doesn't depend on TMDB. Holding it for the instructor's word, since TASK 006 orders Part B first.

## Questions for the instructor

1. Read the live TMDB API terms and site terms (you have web access outside Jio's block) and confirm the ML/AI wording and the current attribution notice.
2. Proceed with Phase 4 under a strict "TMDB data never enters any model" rule (with Model B excluding manual entries)? Or change approach: a different metadata source, or a TV/movie tracker without TMDB?
3. Remove Phase 11's TMDB-based TV Model A from scope?
4. May Part C go ahead now, independently of the TMDB decision?

## Next

- Nirav: switch Windows to encrypted DNS (fixes the TMDB block, and probably the earlier Atlas DNS timeouts). Create the TMDB token only if Phase 4 continues with TMDB.
- Instructor rules on questions 1–4.
