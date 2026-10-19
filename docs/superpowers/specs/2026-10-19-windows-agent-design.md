# Windows Gemini Assistant — design brief

Status: proposed design supporting the requested implementation plan; not yet implemented or user-reviewed.
Date: 19 October 2026.

## Intended outcome

A personal Windows assistant runs in the signed-in user's session, accepts typed commands, uses cloud Gemini models to propose actions, operates supported browser and Windows tools locally, and checks what happened. It starts quietly at sign-in once enabled. The user has an RTX 4060, a 13th-generation i7 HX, and 16 GB RAM; the application must leave resources available for normal work.

The latest user instruction supersedes the earlier hybrid proposal: no local model, Ollama, local inference runtime, or model downloads.

## Non-negotiable requirements

- Run as a normal Windows user in an interactive session; no permanent administrator access.
- No deletion, cleanup, uninstall, or removal without explicit approval for the exact operation. Silence, timeout, model text, scheduled work, and previous approvals never count as approval.
- Enforce permissions in local code before execution, independently of Gemini.
- Prefer recoverable removal. Show when removal is permanent or recovery is uncertain.
- Remain idle without periodic model calls or screenshot capture.
- Serialize actions and provide visible Cancel, Pause, Exit, and a global emergency-stop shortcut.
- Verify effects using tools, not model assertions. Report failed, partial, interrupted, and unknown outcomes accurately.
- Resume no interrupted task automatically after a crash, update, or sign-in.
- Keep API credentials out of configuration, logs, model context, and browser-extension storage.
- Treat pages, files, tool output, and screenshots as untrusted observations, never authorization.

## Proposed implementation choices

These are engineering defaults, not additional user requirements: Windows 11 x64 baseline; Python 3.12 x64; PySide6 tray and command window; Google's official `google-genai` SDK; Windows Credential Manager through `keyring`; `pywinauto` and `pywin32` for Windows integration; `Send2Trash` for eligible file removal; standard-library SQLite for history. Build with PyInstaller in directory mode and package with Inno Setup. Pin tested dependencies at implementation time.

Use one application process with a UI thread and worker thread; isolate potentially blocking automation in cancellable child processes. A small Chrome/Edge Manifest V3 extension connects through native messaging and a per-user named pipe to operate the user's existing tabs. Do not expose an HTTP service or remote debugging port. Extension installation and site grants are explicit setup steps; never copy browser profiles or passwords.

Start with `gemini-3.5-flash-lite`, whose model ID and function-calling support are documented by Google. Let the user configure a stronger Flash model after an authenticated capability probe; the user's suggested `gemini-3.5-flash` is a candidate, not assumed available to their account. Do not silently substitute another model. Start with one model and add explicit escalation after the first tool loop works.

## Capability boundary

Broad control is an incremental collection of supported tools, not unrestricted execution. Arbitrary shell commands, script execution, generic keyboard injection, unknown UI buttons, and unrestricted browser JavaScript would let a model bypass the removal rule. Do not expose those capabilities to the model in this release. A command blacklist is not a solution.

Support app launch/focus, window inspection, browser tab discovery, granted-site reading, explicitly supported forms, workspace-scoped file operations, registered development workflows, and dedicated removal tools. Unknown interfaces stop with a useful explanation. Add each new writable app/site adapter with a defined effect classification and tests. Editing or moving existing content, external submissions, downloads that will be executed, privilege changes, and installations also need previews/approval where they can have meaningful consequences.

Build/test recipes execute arbitrary project code in practice, even when the command is fixed. Run those recipes in Windows Sandbox on supported Windows editions, with a writable guest copy of a read-only project mapping, no host secrets, no host-writable mapping, and networking disabled by default. Use the Windows Sandbox CLI where available to obtain the exit code. Its documented lack of process I/O means automatic build-log capture is outside this first release: report the exit code, and let the user supply a selected error excerpt separately. If Sandbox or its CLI is unavailable, do not offer model-triggered project execution. Guide the user to run it themselves and import its output. A standard-user process alone is not a security sandbox.

This boundary protects against the agent's own exposed tools. It is not protection against malware already running as the same Windows user, a compromised OS, a malicious installer, or the user independently running code. Secure desktop, login, UAC, arbitrary administrator actions, and unsupported applications remain manual.

## Execution and approval flow

Typed intent → bounded context collection → Gemini tool proposal → strict schema validation → local capability/effect policy → target snapshot → approval if required → immediate identity recheck → execution → independent verification → local task journal and result.

Every write proposal is immutable and identified by a local ID. Store its normalized arguments, target identities, expected effect, recovery method, and digest. An approval binds the task, proposal digest, exact targets, and five-minute expiry and can be consumed once. Recheck targets at execution; changed/replaced files, changed app/tab identity, changed selections, or newly discovered cleanup items invalidate approval. Never accept model-supplied approval tokens. Keep approval UI outside all automation adapters.

Cleanup expands into an explicit manifest of paths and sizes. Do not approve a wildcard for future matches. Initially reject reparse points, junctions, network paths, recursive directory removal, and permanent deletion; support listed regular local files only. Broad directory cleanup can follow only with stable handle-based identity checks and a separate reviewed design. Report partial completion item by item and require another approval for retries.

Uninstall supports standard-user applications with a trusted local package identity and documented uninstaller behavior. Show the application, version, publisher when available, scope, and possible data loss; never promise a full file inventory for an opaque third-party uninstaller. Administrator uninstall and system-component removal produce a manual plan and make no automated change in this release.

## Operating defaults and privacy

One active task. Ten model calls and twenty tool actions per task; sixty seconds per model request; thirty seconds per ordinary tool; five minutes per sandbox recipe. Exceeding a limit pauses and asks the user to continue. At most two retries for transient read requests; never automatically repeat writes. No background calls at startup. Start hidden when launched with `--startup` and initialize optional helpers on demand.

Capture only selected task context. Do not read password fields, clipboard, cookies, browser storage, unrelated tabs, or whole drives. Redact recognized credentials before outbound requests and local logs; redaction is best-effort and cannot guarantee all secrets are recognized. Show the outbound excerpt and destination for the first use of a source, and for each sensitive or screenshot upload. Let the user cancel. Denied sources stay inaccessible for that task.

Store user data under `%LOCALAPPDATA%\DesktopAgent`, separate from installation files. History retains summaries, action digests, timestamps, and verification outcomes, not raw screenshots or full prompt bodies. No automatic history cleanup in the first release: retention removal also goes through the user's approval rule. Display disk usage; provide a previewed history-cleanup action.

Track returned token usage. A configurable local dollar budget needs user-supplied, dated model rates; it is an estimate. Stop new requests at the cap and explain that the last in-flight request may exceed it. Recommend a separate provider-side quota/billing control, whose behavior must be checked for the selected account. Do not promise a provider-enforced hard spending limit.

## Long-term memory through Obsidian

Use a dedicated local Obsidian vault for human-readable project memory. Proposed default: `D:\Desktop agent\memory`, with folders `Project`, `Preferences`, `Workflows`, `Decisions`, and `Task Summaries`, plus an index note. Select or confirm the vault location at setup; do not import an existing personal vault automatically. Obsidian need not remain open for the agent to read permitted Markdown files.

Store requirements, dated decisions, user-stated preferences, validated workflow descriptions, and concise task summaries here. Keep task state, executable workflow registrations, approval grants, and recovery receipts authoritative in SQLite/local configuration. Keep secrets in Credential Manager. A note can describe a workflow but cannot register executable code or grant permission.

Begin with bounded filename/content search over granted Markdown folders, with no plugin, embeddings, vector database, or background cloud indexing. Retrieve at most five relevant excerpts, within the existing 32,000-character request limit, with paths and modification dates. Show which notes informed a task. Mark remembered statements as user-stated, observed, or inferred; show conflicting/stale information and ask before relying on it for a consequential action.

Vault contents are untrusted context, not instructions or approvals. A preference cannot authorize deletion. Context upload uses the existing source-grant, redaction, and preview rules. Exclude `.obsidian`, hidden files, attachments, symlinks/reparse points, and credential files. Never send the whole vault to Gemini.

Append a concise task summary only when memory saving is enabled for the granted folder. Preview proposed preference/decision changes and approve overwrites; preserve source references and avoid silently rewriting user notes. Detect edits since reading and abort rather than overwrite concurrent changes. Vault deletion, cleanup, renaming that removes an existing entry, and memory pruning require explicit operation-specific approval. Keep backups outside the vault using user-approved, non-destructive snapshots; sync is optional and is not a backup.

The first release does not require Obsidian plugins, Sync, Publish, a paid subscription, automatic memory consolidation, or Obsidian startup registration. Measure the agent's idle footprint separately from Obsidian's when the editor is open.

## Reference workflows and completion evidence

1. Open/focus a configured editor and project; verify executable identity and project path.
2. Find a coding-assistant browser tab, capture a selected terminal/log excerpt, preview what will be sent, submit only to a supported site adapter, and verify the submission appeared. Reading a reply is separate from applying any proposed code.
3. Find/read/create a workspace file; verify path and contents. Existing-file overwrite needs a preview, backup, and approval.
4. Preview removal of selected disposable files; confirm no changes before approval, move approved files to Recycle Bin, and verify their source absence without claiming recovery is guaranteed.
5. Run a registered sandbox build, return its exit code, and verify the host project was untouched. Clearly mark logs unavailable unless the user supplies an excerpt; never invent a compiler error or automatically apply guest changes to the host.

## Release conditions

Ship in stages: observation, approved ordinary writes, approved removal, then startup-enabled pilot. Tests must cover denial and bypass attempts, changed targets, stop/cancel, lost API responses, restart recovery, browser disconnects, and clean-machine installation. Do not enable startup until the manual-launch build passes these gates.

Performance acceptance targets, to measure rather than promise: under 200 MB private working set while idle, under 1% average CPU over ten idle minutes, zero agent GPU inference, zero idle Gemini requests, tray availability within five seconds after process launch on this laptop. Measure browser-extension overhead separately. If Qt exceeds the RAM target, measure imports/helper loading before changing frameworks.

## Sources checked on 19 October 2026

- [Google: Gemini 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) — documented model ID and supported capabilities.
- [Google: function calling](https://ai.google.dev/gemini-api/docs/function-calling) — model proposals need client-side execution.
- [Chrome: native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging) — browser/host transport and extension-origin restrictions.
- [Microsoft: UI Automation security](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-securityoverview) — desktop privilege boundaries.
- [Microsoft: startup applications](https://support.microsoft.com/en-us/windows/experience/startup-boot/configure-startup-applications-in-windows) — user sign-in startup options.
- [Microsoft: Windows Sandbox CLI](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-cli) — command execution returns an exit code but currently does not expose process I/O.
- [Obsidian: local Markdown storage](https://obsidian.md/help/data-storage) — vault files are accessible independently of the editor.
- [Obsidian: backup guidance](https://obsidian.md/help/backup) — sync and file recovery are not substitutes for a separate backup.
