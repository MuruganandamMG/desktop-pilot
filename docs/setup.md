# Development setup

Requires Windows and Python 3.12 or newer. From the feature checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m desktop_agent --status
.\.venv\Scripts\python.exe -m desktop_agent
```

The native window is a read-only cloud preview. It searches local memory and can call Gemini after an explicit preview and consent. Only the constant `runtime_status` tool is registered; it does not inspect or change Windows, browsers, or files. No removal tools or startup registration are enabled. Raw prompts and model answers are not retained in the journal; task states, action receipts and usage metadata are retained.

Nonsecret settings and the SQLite journal live under `%LOCALAPPDATA%\DesktopAgent`. The `vault_path` setting points to the private vault. No API key is needed for local search or `--status`. Never paste a real key into tests, a GitHub issue, a chat, the vault, or repository files.

## First Gemini connection

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

`main` contains bootstrap documentation. Work is isolated on `feat/foundation-workflow`; each coherent tested change is committed and pushed. A draft pull request tracks this milestone. Future work should fetch current branches, inspect the working tree, and follow `AGENTS.md`. Never force push or automatically merge. Hosted CI checks run for pushes/PRs; branch-protection rules are not configured by this application.

When a new checkout is used, recreate its environment; do not commit/copy `.venv`, local settings, history, or the vault. Normal Python bytecode and test caches are ignored. Do not run cleanup tools merely to make Git status look clean.

SDK integration references: [official manual function calling](https://googleapis.github.io/python-genai/), [Gemini usage metadata](https://ai.google.dev/api/generate-content#UsageMetadata). SDK transport and model-loop tests use synthetic offline responses; passing them does not establish live model access or real billing behavior.
