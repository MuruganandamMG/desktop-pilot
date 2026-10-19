# Development setup

Requires Windows and Python 3.12 or newer. From the feature checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m desktop_agent --status
.\.venv\Scripts\python.exe -m desktop_agent
```

The current native window is a foundation preview: it records paused task states and searches local memory. It does not execute saved requests, call Gemini, control Windows/browser apps, remove files, or register startup. It deliberately does not retain raw requests, so requests must be re-entered once execution is implemented.

Nonsecret settings and the SQLite journal live under `%LOCALAPPDATA%\DesktopAgent`. The `vault_path` setting points to the private vault. Credential access is implemented but no API key is required for the offline preview. Never paste a real key into tests, a GitHub issue, the vault, or repository files.

## Local Obsidian setup

For this workstation the private vault is `D:\Desktop agent\memory`, with an index and Project, Preferences, Workflows, Decisions, and Task Summaries folders. This folder is excluded from Git. Obsidian has a local registration for it; no sync, community plugins, financial wallet, or Obsidian startup behavior was configured.

The preview searches these named folders on demand, reads at most 1,000 files, excludes hidden/reparse paths and non-Markdown files, skips files larger than 256 KiB, and returns at most five excerpts. Note provenance is a claim in the note, not authenticated user authorization. There is no automatic memory writing or cloud upload yet.

## Git workflow

`main` contains bootstrap documentation. Work is isolated on `feat/foundation-workflow`; each coherent tested change is committed and pushed. A draft pull request tracks this milestone. Future work should fetch current branches, inspect the working tree, and follow `AGENTS.md`. Never force push or automatically merge. Hosted CI checks run for pushes/PRs; branch-protection rules are not configured by this application.

When a new checkout is used, recreate its environment; do not commit/copy `.venv`, local settings, history, or the vault. Normal Python bytecode and test caches are ignored. Do not run cleanup tools merely to make Git status look clean.
