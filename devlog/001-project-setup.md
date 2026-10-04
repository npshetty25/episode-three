# 001 — Project setup and MongoDB Atlas connection

- **Date:** 2026-10-03 to 2026-10-04
- **Requested by:** Nirav (before the instructor workflow started)
- **Status:** Done. All follow-ups closed (Nirav confirmed 2026-10-04).

## Summary

Set up the local Python project, a free MongoDB Atlas cluster, MongoDB Compass, secret handling with `.env`, and a private GitHub repo. Python has not connected to Atlas yet. That is the next task.

## Changes

| File / resource | Change |
|---|---|
| `episode-three/` | New project folder, `git init` (branch `master`) |
| `venv/` | Virtual environment, Python 3.13.5. Not committed. |
| `.gitignore` | Ignores `venv/`, `.env`, `__pycache__/`, `*.pyc`, `.ipynb_checkpoints/` |
| `requirements.txt` | `dnspython==2.8.0`, `pymongo==4.18.2`, `python-dotenv==1.2.4` |
| `.env` | Git-ignored. One key: `MONGODB_URI` (Atlas `mongodb+srv://` string) |
| `../.vscode/settings.json` | Outside the repo. Points VS Code at the venv interpreter and auto-activates it in new terminals |
| pip (inside venv) | Upgraded 25.1.1 → 26.2.1 |
| MongoDB Atlas | Organization `epsiode3`, project `Episode3`, cluster `Cluster0`: FREE tier, AWS, 1 region, MongoDB 8.0.34. One database user. Sample dataset loaded (`sample_mflix.movies` = 21,349 docs). |
| MongoDB Compass | 1.52.0 installed. Saved connection named `Episode3 Atlas` |
| GitHub | Private repo `npshetty25/episode-three`, remote `origin` |

## Environment facts the instructor should know

- Windows 11, PowerShell, VS Code with Claude Code. Python 3.13.5, Git 2.52, GitHub CLI 2.83 (logged in as `npshetty25`).
- Atlas free tier limits: 512 MB storage, 100 ops/sec, 500 connections, 10 GB in and 10 GB out per 7 days, no backups, auto-paused after 30 days with zero connections.
- The region chosen at cluster creation was not recorded. AWS Mumbai (ap-south-1) was recommended; confirm in Atlas.
- **Storage already used: 142.99 MB of 512 MB (28%)**, almost all of it the sample dataset (`sample_mflix` etc.). Keep it for query practice; drop the `sample_*` databases before large-scale data collection if the storage estimate needs the room.

## Verification

| Check | Result |
|---|---|
| `pip install pymongo python-dotenv` | Success; dnspython installed automatically as a pymongo dependency |
| `git check-ignore -v .env` | Ignored by `.gitignore` line 2 |
| `.env` format (key name and booleans only, no values printed) | Key `MONGODB_URI`, value starts with `mongodb+srv://`, no `< >` placeholders left |
| Compass → Atlas | Connected; browsed `sample_mflix.movies` |
| Python → Atlas | **Not tested yet** (task 002) |

## Failures and issues

1. **Research workflow failed.** All 4 background research agents stopped on the session usage limit and returned nothing. *Fix:* researched manually (Atlas docs, PyPI, Compass download page). *Status:* resolved.
2. **Wrong claim in a docs summary.** A summary of the PyMongo "Get Started" page said dnspython must be installed separately. PyPI metadata shows `dnspython<3.0.0,>=2.7.0` is a required dependency, and the pip output confirmed it installed automatically. *Status:* resolved.
3. **`.env` missing its key.** The file held only the raw connection string, so `os.getenv("MONGODB_URI")` would have returned `None`. *Fix:* added the `MONGODB_URI=` prefix. *Status:* resolved.
4. **Database password exposed twice in the chat.** (a) A `.env` format check printed the whole line, because the check expected `KEY=value` and the key was missing. (b) Selecting text in `.env` inside VS Code sent it to the assistant. *Fix:* password rotated once; a second rotation is pending after (b). *Prevention:* checks on `.env` print only key names and booleans; never select text in `.env` during a chat. *Status:* **open**, waiting on the second rotation.
5. **VS Code popup** ("installed packages into your global environment"). *Cause:* VS Code's interpreter was the system Python, because the venv sits in a subfolder of the workspace. *Fix:* `.vscode/settings.json`, plus **Python: Select Interpreter** → `episode-three\venv\Scripts\python.exe`. *Status:* waiting for Nirav to confirm.
6. **Git warning** "LF will be replaced by CRLF". Harmless Windows line-ending conversion. No action.

## Decisions

- Atlas free tier instead of a local MongoDB server: nothing to install and nothing to keep running.
- PyMongo synchronous driver, not the async one.
- Student benefit: claim the free certification voucher; skip the $50 Atlas credit, which needs a card and isn't used by the free tier.
- GitHub repo stays private until the README and first model are presentable.
- Java/JavaFX dropped from priorities (2026-10-03).

## Follow-up (2026-10-04)

- Atlas dashboard checked: cluster ACTIVE, FREE tier, 3/500 connections (Compass), backups and auto-scaling OFF as expected for the free tier.
- Nirav given steps for **Python: Select Interpreter**; not yet confirmed.
- Added check: Atlas IP Access List must contain only Nirav's own IPs, with no `0.0.0.0/0`, because the password was exposed. Not yet confirmed.

- **Closed:** Nirav confirmed the password was rotated a second time (`.env` and Compass updated), the venv interpreter is selected in VS Code, and the IP Access List was checked. Issues 4 and 5 are resolved.

## Next

- Task 002: first Python script that loads `.env`, connects to Atlas and runs `ping`.
- Receive the full project handoff document from the instructor.
