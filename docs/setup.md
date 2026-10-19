# Development setup

Requires Windows and Python 3.12 or newer. From the active checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m desktop_agent --status
.\.venv\Scripts\python.exe -m desktop_agent
```

Default launch is a terminal voice agent. The optional `--gui` legacy native window is a read-only cloud preview. It searches local memory and can call Gemini after an explicit preview and consent. Only the constant `runtime_status` tool is registered; it does not inspect or change Windows, browsers, or files. No removal tools or startup registration are enabled. Raw prompts and model answers are not retained in the journal; task states, action receipts and usage metadata are retained.

Nonsecret settings and the SQLite journal live under `%LOCALAPPDATA%\DesktopAgent`. The `vault_path` setting points to the private vault. No API key is needed for local search or `--status`. Never paste a real key into tests, a GitHub issue, a chat, the vault, or tracked repository files.

## Local .env configuration

The development checkout loads `GEMINI_API_KEY` and explicit voice settings from its root `.env`, next to `pyproject.toml`. Lookup order is the process environment, then that project file, then Windows Credential Manager. Empty values fall through to the next source. A nonempty invalid value fails instead of silently selecting another credential.

The ignored local `.env` is ready for your key; `.env.example` is a tracked empty template. Only `GEMINI_API_KEY`, `GEMINI_LIVE_MODEL`, `VOICE_INPUT_DEVICE` and `VOICE_OUTPUT_DEVICE` are read. Quotes, optional `export`, and inline comments are supported; interpolation, command execution, parent-directory search, and loading unrelated variables are not. Malformed, duplicated, oversized or reparse/symlink key files fail with a generic error that excludes secret values. The file limit is 64 KiB and the key limit is 4,096 characters.

Adding a key to `.env` does not save it to Credential Manager, mutate the process environment, or trigger an API call. The GUI key-save action still writes to Credential Manager; remove/clear an overriding environment setting yourself if you intend the saved credential to be used. This plaintext development file is not an encrypted credential store. Installed packages without the source checkout's `pyproject.toml` use process variables/Credential Manager rather than searching working directories for `.env`.

## Terminal voice (default)

Voice can now open detected **Notepad, Calculator, Chrome, Edge, VS Code and Obsidian**. Say "Open Chrome" or "Open VS Code". Only apps found in known installation locations are offered. Launch receipts do not certify window visibility or focus. Arbitrary shell commands, app arguments, file changes, removals and unsupported app control remain unavailable. Restart an older running agent to load the new tool declarations.

Close the old Desktop Pilot window first; all modes share one instance lock. Run `.\.venv\Scripts\python.exe -m desktop_agent` from `D:\Desktop agent`. Launch starts local speech controls and a Gemini Live voice session automatically. No visible window or web server opens; no Enter-to-start is required.

Set `GEMINI_API_KEY` in the ignored root `.env`. `GEMINI_LIVE_MODEL` defaults to `gemini-3.8-live`; set an accessible native audio Live model if your account does not support it. No silent substitution occurs. The legacy text model setting is independent. Optional `VOICE_INPUT_DEVICE` and `VOICE_OUTPUT_DEVICE` are numeric device IDs from `.\.venv\Scripts\python.exe -m desktop_agent --list-audio-devices`. Blank selects Windows defaults. Use a headset: acoustic echo cancellation is not claimed.

- Speak normally: Gemini listens and replies aloud.
- Say **Pilot pause**: disconnect cloud audio; Windows still listens locally for the three control phrases.
- Say **Pilot resume**: reset pending approvals and start a fresh cloud conversation.
- Say **Pilot exit**: close cloud audio, local recognition, playback and the app.
- Ctrl+C or Ctrl+Alt+Pause remain emergency fallbacks.

Local controls require an installed English Windows speech recognizer and use the Windows default microphone. Set it to the same input you use for conversation. Windows synthesis supplies short status announcements; Gemini supplies normal spoken answers. Use a headset to avoid speaker feedback. The fixed helper follows the computer's PowerShell execution policy, with no policy bypass or system configuration change. Missing recognition support or blocked helper execution prevents hands-free launch rather than silently dropping voice controls.

Microphone speech streams directly to Google and cannot be redacted locally before transmission. Audio is not recorded. Redacted/control-character-filtered transcripts appear in the terminal but are not persisted. Terminal events show connect/turn/error/usage activity plus a five-second streaming heartbeat. Session metadata is journaled without raw speech. No tool is declared for voice; unsolicited function calls are denied without effects. Computer actions and memory attachment are not yet integrated into voice.

Sessions stop at ten minutes or twenty model-completed turns. Disconnect, device failure, spoken pause and session lock end cloud audio without reconnecting automatically. Say **Pilot resume** to start again. Lock closes local recognition too; after unlock, local control listening returns but cloud audio requires a fresh spoken resume. Missing session monitoring disables cloud/audio. Existing dollar-budget settings disable Live because matching voice rates are not configured; elapsed time and provider usage are not a spending guarantee.

The terminal requires interactive Windows input. `--status` and `--list-audio-devices` work offline. `--gui` explicitly opens the old preview; its text-model instructions follow below. No startup behavior is enabled.

## Legacy GUI: first Gemini connection


1. Launch the application and choose **Set API key locally**. Enter your Gemini API key in that password field; it is stored through Windows Credential Manager. Saving it makes no API request.
2. Keep the model ID `gemini-3.5-flash-lite`, or enter an exact ID available to your account. There is no silent switch to a latest-model alias.
3. Choose **Preview and test model**, inspect the destination, model, task content and limits, then send if correct. This is a real, potentially billable request. A successful probe verifies a structured call from the selected model and executes only the constant local runtime-status read. A probe never certifies a different fallback model.
4. Type a request and choose **Preview and ask Gemini**. Review the redacted task content before sending. Cancel is the default in the preview; declining it creates no task and sends nothing.
5. To share memory, first search locally, explicitly select **Attach the last local search excerpts**, then inspect the next cloud preview. With the checkbox off, no note excerpts are included. Notes and tool output remain untrusted data.

Use **Cancel cloud task** to stop waiting and prevent subsequent tools/requests. A request already received by Google may still be billed. Closing the window during a task requests cancellation and closes when the worker returns. The per-user runtime lock prevents a second app instance from resetting live task state.

Model text is displayed as unverified advice. It is never accepted as evidence that a computer action happened. Missing keys, auth errors, quota errors, unknown tools, non-read proposals, changed targets, duplicate calls, unapproved tool observations and uncertain tool outcomes pause/fail safely; there is no automatic write retry or restart resume.

## Request limits and estimated cost

Defaults: ten actual API attempts per task including retries, twenty tool actions, 1,024 output tokens per response, a sixty-second request deadline, and at most 32,000 characters of serialized request context. SDK automatic function execution and automatic continuations are disabled. Transient requests can retry at most twice only when no estimated dollar cap is configured. Returned token counts include prompt, tool-use prompt, candidate and thought usage in their appropriate input/output groups; unavailable counts are shown as unavailable.

Optional nonsecret settings fields are `budget_usd` (per-task decimal string), `rate_model_id`, `input_rate_usd`, `output_rate_usd` (USD per million tokens), and `rate_date` (ISO date). These rates must be supplied and dated by the user from their actual provider pricing; the app does not invent prices. If a cap exists without matching dated rates, or a response's billable usage is unknown, new requests are blocked. With a cap, requests are not retried internally because a lost response may already be billable. The final in-flight request can exceed the estimate; this is not a provider-enforced spending limit. Estimates do not include taxes, discounts, exchange rates, or charges not represented by the configured rates.

Optional `stronger_model_id` enables a single explicitly chosen escalation for invalid reasoning before any tool executes, after separately checking that model with the opt-in probe. There is no escalation for auth/quota/provider blocks, after effects, or during a model probe. All requests still share the task's limits and source consent. No stronger model is configured by default.

## Local Obsidian setup

For this workstation the private vault is `D:\Desktop agent\memory`, with an index and Project, Preferences, Workflows, Decisions, and Task Summaries folders. This folder is excluded from Git. Obsidian has a local registration for it; no sync, community plugins, financial wallet, or Obsidian startup behavior was configured.

The preview searches these named folders on demand, reads at most 1,000 files, excludes hidden/reparse paths and non-Markdown files, skips files larger than 256 KiB, and returns at most five excerpts. Note provenance is a claim in the note, not authenticated user authorization. There is no automatic memory writing or whole-vault cloud upload.

## Git workflow

PR #1 was merged and the user now authorizes development directly on `main` in `D:\Desktop agent`. Each coherent tested change is committed and pushed to `origin/main`. Fetch and inspect divergence/local edits before work; follow `AGENTS.md`. Existing feature worktrees are retained but are not the active checkout. Never force push or automatically rewrite shared history. Hosted CI checks run for pushes/PRs; branch-protection rules are not configured by this application.

When a new checkout is used, recreate its environment; do not commit/copy `.venv`, local settings, history, or the vault. Normal Python bytecode and test caches are ignored. Do not run cleanup tools merely to make Git status look clean.

SDK integration references: [official manual function calling](https://googleapis.github.io/python-genai/), [Gemini usage metadata](https://ai.google.dev/api/generate-content#UsageMetadata). SDK transport and model-loop tests use synthetic offline responses; passing them does not establish live model access or real billing behavior.
