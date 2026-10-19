# Windows Gemini Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execution recommendation for this project: native implementation using executing-plans; use subagents only if the user explicitly chooses them.

**Goal:** Deliver a lightweight Windows startup assistant that uses cloud Gemini to perform supported local tasks, verifies results, and always obtains explicit approval before removal.

**Architecture:** One per-user tray application owns the task state, approval UI, model requests, and execution policy. Windows adapters and a browser native-messaging extension perform bounded actions behind the same executor. SQLite records progress so interrupted work pauses safely after restart.

**Tech Stack:** Python 3.12 x64, PySide6, google-genai, keyring, pywin32, pywinauto, Send2Trash, SQLite; local Markdown memory edited through Obsidian; Chrome/Edge Manifest V3 extension with plain JavaScript; pytest/pytest-qt, PyInstaller, Inno Setup; Windows Sandbox for untrusted build recipes where supported.

**Spec:** [Proposed design brief](../specs/2026-10-19-windows-agent-design.md). Both documents are planning artifacts requested by the user; neither constitutes approval to install, enable startup, or execute the plan.

## Global Constraints

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

## Review Focus

1. A file is replaced or becomes a junction after preview: reject stale approval rather than remove a different target; Tasks 3 and 9.
2. An apparently harmless build/script or UI action performs removal indirectly: deny unrestricted execution and isolate project recipes; Tasks 6, 7, and 8.
3. The API times out after an action succeeded: do not repeat the action or claim failure without inspecting effects; Tasks 4 and 10.
4. The user switches tabs/windows, locks Windows, or presses Stop while an operation waits: pause, discard stale targets, and stop subsequent writes; Tasks 5, 7, and 10.
5. A browser page/model/tool response supplies fake approval or asks to disable policy: preserve the user boundary and reject it; Tasks 3, 4, and 7.

## Scope and staged delivery

The workspace was empty on inspection. No existing callers, fixtures, exports, or configuration need migration. This plan creates the application, shared contracts, tests, browser bridge, packaging, and operator documentation together. It does not download a local model or register startup during planning.

| Stage | User-visible result | Prerequisite |
|---|---|---|
| A | Launch manually, configure Gemini, inspect windows/tabs, get proposals | Tasks 1–5 and read-only parts of 6–7 |
| B | Launch/focus apps, manage granted files, submit a previewed assistant message, run isolated recipes | Tasks 6–8 and 10 |
| C | Preview and approve file removal/cleanup and supported app uninstall | Task 9 plus policy regression tests |
| D | Packaged install, sign-in startup, recovery, measured pilot | Tasks 11–13 |
| Memory | Relevant project notes retrieved and saved through a granted Obsidian vault | Task 14; integrate before Task 13 acceptance |

Each stage must work before extending write permissions. Tasks are sequential by default; do not build a plugin marketplace, remote-control server, general agent framework, or multi-agent router.

## File map

```text
pyproject.toml                       dependency declarations, desktop-agent entry point
src/desktop_agent/
  __main__.py                       CLI entry; app and native-host modes
  app.py                            UI lifecycle, worker lifecycle, single instance
  contracts.py                      shared immutable records, enums, strict parsing
  settings.py                       validated preferences and Credential Manager access
  store.py                          SQLite task journal and approval consumption
  policy.py                         capability registry and effect classification
  approvals.py                      immutable previews, identity checks, single-use grants
  executor.py                       only dispatch path to tool implementations
  model.py                          official Gemini SDK integration and usage limits
  context.py                        source selection, redaction, payload bounding
  memory.py                         bounded Markdown search and conflict-safe note proposals
  runner.py                         bounded model/tool loop and cancellation
  ui.py                             command/history/settings/approval/tray views
  windows.py                        approved apps, identity snapshots, UIA observation
  files.py                          granted-root reads, writes, backup, recycle previews
  browser.py                        browser RPC, tab identity, site adapter registry
  native_host.py                    framed native messaging and named-pipe bridge
  recipes.py                        registered workflow definitions and sandbox runner
  uninstall.py                      supported per-user app inventory and uninstall plans
  startup.py                        sign-in shortcut and stop-hotkey registration
extension/
  manifest.json                     MV3 permissions and optional site grants
  background.js                     reconnect, native transport, tab operations
  content.js                        bounded reads and supported site form adapter
  popup.html, popup.js               connect state and explicit site permission grants
tests/
  test_contracts.py, test_settings.py, test_store.py, test_policy.py
  test_approvals.py, test_model.py, test_context.py, test_runner.py
  test_ui.py, test_windows.py, test_files.py, test_browser.py
  test_native_host.py, test_recipes.py, test_uninstall.py, test_startup.py
  test_memory.py                    vault grants, retrieval, injection, concurrent edits
  fixtures/                         synthetic pages, tool outputs, secret samples
  acceptance.md                     clean-Windows and real-desktop manual checks
extension/tests/bridge.test.mjs      Node built-in test runner; no JS framework
packaging/
  desktop-agent.spec                 PyInstaller directory build
  installer.iss                     per-user installer, registrations, upgrade handling
  native-host-manifest.json          generated absolute executable and allowed origins
docs/
  setup.md, supported-tools.md, troubleshooting.md, threat-model.md
```

Do not pre-create empty modules; add each when its task needs it. Keep dependencies pinned to tested versions and record license obligations in the packaged release.

## Shared contracts

Use frozen dataclasses and string enums; validate every SDK/IPC JSON boundary with explicit field/type/size checks. No model-provided Python object is executable.

- `Action(id: str, task_id: str, tool: str, arguments: dict)` contains no approval field.
- `Target(identity: str, display: str, fingerprint: str)` is derived locally, never trusted from the model.
- `Proposal(action: Action, effect: Effect, targets: tuple[Target, ...], digest: str, recovery: str)` is immutable.
- `Effect` = `READ`, `WRITE`, `REMOVE`, `EXTERNAL_SEND`, `PRIVILEGED`, `UNSUPPORTED`.
- `Approval(id: str, task_id: str, digest: str, expires_at: float, consumed: bool)` stays local.
- `Result(status: str, summary: str, evidence: dict)` has status `verified`, `failed`, `partial`, `unknown`, or `cancelled`.
- `TaskState` = `QUEUED`, `PLANNING`, `WAITING_APPROVAL`, `EXECUTING`, `VERIFYING`, `PAUSED`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `INTERRUPTED`.
- `ToolSpec` contains its strict input schema, local classifier, `prepare(action) -> Proposal`, `execute(proposal, cancel) -> Result`, and `verify(proposal, result) -> Result`. Register these explicitly; no dynamic imports from model names.
- `CancelToken` wraps a thread-safe event; workers inspect it before every side effect. Stop prevents new effects; it cannot undo an effect already completed.

## Task 1: Runnable application and persisted task lifecycle

**Files:** Create `pyproject.toml`, `__main__.py`, `app.py`, `contracts.py`, `store.py`; tests `test_contracts.py`, `test_store.py`.

**Interfaces:** `Store.create_task(command: str) -> str`; `Store.transition(task_id: str, state: TaskState) -> None`; `Store.interrupt_inflight() -> int`; `main(argv: list[str] | None = None) -> int`.

- [ ] Write tests: reject unknown action fields/types; disallow invalid state transitions; preserve completed evidence across reopen; turn in-flight tasks into INTERRUPTED without executing tools.
- [ ] Run `python -m pytest tests/test_contracts.py tests/test_store.py -q`; confirm the tests fail for missing implementation.
- [ ] Add a virtual environment and package metadata, shared records, SQLite transactions/schema version 1, local app-data directories, and a manual-launch window. Do not store full prompts by default.
- [ ] Run the tests and launch `python -m desktop_agent`; expected: tests pass, window opens, closing/reopening preserves task summaries.
- [ ] Commit this deliverable if Git is initialized for implementation; do not initialize Git merely to save planning documents.

## Task 2: Settings, Gemini key storage, and outbound context boundary

**Files:** Create `settings.py`, `context.py`; tests `test_settings.py`, `test_context.py`, synthetic fixtures.

**Interfaces:** `load_settings() -> Settings`; `save_settings(settings: Settings) -> None`; `get_api_key() -> str | None`; `set_api_key(value: str) -> None`; `prepare_context(sources: list[Source], grants: set[str]) -> ContextBundle`. Define `Source` and `ContextBundle` in `contracts.py` here.

- [ ] Test absent/invalid settings; key round trip with a mocked credential backend; no key in serialized settings; denied source excluded; recognized secrets/password fields omitted; output bounded to 12,000 characters per observation and 32,000 per request.
- [ ] Run the targeted tests and confirm failure.
- [ ] Implement default workspace grants as empty, model ID `gemini-3.5-flash-lite`, 1,024 output tokens per response, ten calls/twenty actions per task, and a sixty-second API timeout. Add source preview data and key deletion as a previewed removal operation, never an implicit settings reset.
- [ ] Run tests; expected PASS. Inspect a synthetic outbound preview and logs to confirm fixtures' secrets are absent. Document residual redaction limits.
- [ ] Commit.

## Task 3: Local permission policy and single-use approval

**Files:** Create `policy.py`, `approvals.py`, `executor.py`; extend `store.py`; tests `test_policy.py`, `test_approvals.py`.

**Interfaces:** `classify(action: Action) -> Effect`; `prepare(action: Action) -> Proposal`; `request_approval(proposal: Proposal) -> str`; `record_user_decision(request_id: str, accepted: bool) -> None`; `execute(proposal: Proposal, approval_id: str | None, cancel: CancelToken) -> Result`.

- [ ] Test REMOVE without approval executes zero effects; expiry at 300 seconds; rejection/timeout; task/digest mismatch; second use; altered targets; fake model authorization; unknown tools; Stop before dispatch; duplicate action IDs.
- [ ] Run targeted tests; confirm failure before adding executor behavior.
- [ ] Implement deny-by-default classification and exact proposal digests. Bind approval to task/digest and consume it transactionally before execution; crash after consumption requires inspection and fresh approval. Only local UI events can record decisions; do not expose that function to model/IPC tools.
- [ ] Add tests that generic shell, script, arbitrary UI click/type, browser evaluate, and commands hidden in arguments have no registered capability. Every tool is reachable only through executor dispatch.
- [ ] Run tests; expected PASS with a spy proving unauthorized calls never reach adapters. Commit.

## Task 4: Gemini tool calls, explicit model escalation, and cost controls

**Files:** Create `model.py`, `runner.py`; tests `test_model.py`, `test_runner.py`.

**Interfaces:** `GeminiClient.next_step(context: ContextBundle, history: list[dict], tools: list[dict], model_id: str) -> ModelTurn`; `probe_model(model_id: str) -> CapabilityReport`; `Runner.run(task_id: str, command: str, cancel: CancelToken) -> Result`. Define these return records in `contracts.py`.

- [ ] Test schema-invalid calls are rejected; forged policy instructions have no effect; calls/action caps pause the task; missing key/auth/429/timeout errors are distinct; a write is never automatically retried after network failure.
- [ ] Run targeted tests; confirm failure.
- [ ] Integrate the official SDK using the then-supported documented API surface; disable automatic function execution so every proposal passes Task 3. Preserve function-call IDs and required opaque SDK conversation metadata. Retry transient model reads at most twice with jitter, within the sixty-second request deadline.
- [ ] Add a user-selected stronger-model ID and a function-call probe. Escalate at most once for unsupported/invalid reasoning, with no duplicate action execution; if unavailable, pause rather than silently substitute. Cap tool batches sequentially.
- [ ] Record token usage, model, and dated user-configured price estimates; deny new requests at a configured cap. With no rates, show tokens and "cost estimate unavailable". Stop retrying auth/billing failures.
- [ ] Run mocked tests; opt-in live smoke test with the user's configured key must produce a harmless structured read proposal. Never put a real key in fixtures. Commit.

## Task 5: Command window, approvals, tray, and emergency stop

**Files:** Create `ui.py`; extend `app.py`; tests `test_ui.py`; add manual checks to `tests/acceptance.md`.

**Interfaces:** `MainWindow.submit_command(command: str) -> None`; `ApprovalDialog.show_proposal(proposal: Proposal) -> None`; `AppController.stop_all() -> None`; connect to Task 3 using Qt signals, never a model-facing endpoint.

- [ ] Test a removal preview shows exact items/count/size/reason/recovery; default focus is Cancel; Enter in an unrelated input cannot approve; reject and window close deny; stale proposals refresh; cancellation leaves a visible outcome.
- [ ] Run `python -m pytest tests/test_ui.py -q`; confirm failure.
- [ ] Build one accessible command window with task history, source preview, settings, explicit approval controls, and tray Show/Pause/Exit. Run model/network work outside the UI thread. Show what is supported rather than implying unrestricted computer access.
- [ ] Register Ctrl+Alt+Pause as emergency stop; report conflicts and preserve visible Stop. Block automation of this application's own windows. Session lock pauses execution and invalidates pending approvals; unlock does not resume it.
- [ ] Run UI tests and manually verify keyboard navigation, screen-reader labels, display scaling, hotkey conflict, lock/unlock, and stopping a blocked worker. Commit.

## Task 6: Windows observation, safe app launch, and granted files

**Files:** Create `windows.py`, `files.py`; tests `test_windows.py`, `test_files.py`.

**Interfaces:** `list_windows() -> list[WindowInfo]`; `launch_app(app_id: str, project_id: str | None) -> Result`; `focus_window(window_id: str) -> Result`; `read_file(path: str) -> Result`; `prepare_write(path: str, text: str) -> Proposal`.

- [ ] Test wrong executable identity, ambiguous window title, paths outside grants, traversal, alternate streams, device/UNC paths, symlink/junction escape, executable/script writes, and overwrite without approval are rejected.
- [ ] Run targeted tests; confirm failure.
- [ ] Register user-selected absolute executable paths and structured project arguments, with no shell invocation or arbitrary launch arguments. Allowlist executable behavior: registering a shell, installer, interpreter, or arbitrary project launcher does not make it safe. Inspect UIA trees without harvesting password controls.
- [ ] Support bounded regular-file reads, new plain-text files, and previewed existing-file edits with a non-overwriting backup. Reject unsafe file types and reparse points. Require canonical root and file identity rechecks for writes; verify saved bytes and backup evidence.
- [ ] Run tests; manually open/focus an editor project and create/edit a disposable text file. Confirm an elevated window yields a manual-action explanation. Commit.

## Task 7: Existing Chrome/Edge tabs through a browser extension

**Files:** Create `browser.py`, `native_host.py`, `extension/*`; tests `test_browser.py`, `test_native_host.py`, `extension/tests/bridge.test.mjs`.

**Interfaces:** `BrowserBridge.request(method: str, params: dict, timeout_s: float = 10) -> dict`; native-host mode `desktop-agent --native-host`; methods `tabs.list`, `tabs.focus`, `page.read`, and registered adapter-specific writes.

- [ ] Test malformed/oversized frames, unauthorized extension origins, unknown methods, stale tab/navigation identity, restricted pages, ungranted origins, bridge disconnection, fake approval RPC, and content requesting arbitrary JavaScript.
- [ ] Run Python tests and `node --test extension/tests/bridge.test.mjs`; confirm failure.
- [ ] Implement four-byte little-endian JSON framing; impose a 256 KiB application message cap. Validate sender origin and schema. Bridge via per-user named pipe with user-only ACL and per-connection nonce; credentials never enter the extension. Explain that this does not isolate hostile same-user malware.
- [ ] Use `tabs`, `nativeMessaging`, `scripting`, and `storage` only as needed; request origin access explicitly through the popup with optional HTTP(S) host permissions. Exclude incognito, browser-internal URLs, file URLs, and ungranted sites. Do not continuously scrape pages.
- [ ] Read selected visible page text. For writes, support explicit site adapters only, with stable URL/form identity, effect classification, and postcondition; no generic click/type/evaluate endpoint. Treat page text as data.
- [ ] Run tests, install unpacked in one test browser profile, then test the second browser. Verify tab switching/navigation cancels stale writes. Store distribution and generated extension IDs are packaging inputs, not assumed constants. Commit.

## Task 8: Registered workflows and isolated terminal/build tasks

**Files:** Create `recipes.py`; extend browser site adapter; tests `test_recipes.py`, site fixtures.

**Interfaces:** `run_recipe(recipe_id: str, project_id: str, cancel: CancelToken) -> Result`; `prepare_assistant_submission(tab_id: int, excerpt: str) -> Proposal`.

- [ ] Test project arguments cannot inject shell text; modified recipe identity invalidates approval; build writes cannot reach host workspace; Sandbox absence disables execution; tool output with secrets is redacted; assistant submission needs preview and exact destination.
- [ ] Run targeted tests; confirm failure.
- [ ] Define saved workflows as versioned lists of registered tools, with no LLM required for an exact saved-command match. Saved workflows still use the same permissions. Add "open project" and "share selected error"; import terminal output from a user-selected log or from an isolated recipe, not arbitrary terminal-history scraping.
- [ ] Detect Windows edition, Sandbox feature, and `wsb` CLI support. Start with networking/clipboard disabled and a read-only project mapping; copy into the guest before execution. Use `wsb connect` and `wsb exec` in the existing guest login to run a registered recipe, with a five-minute deadline. Capture the exit code; do not expose a writable host mapping to export results. Do not enable Windows features or elevation automatically. If unavailable, offer manual run/output import.
- [ ] Show "Build logs unavailable: supply a selected excerpt" when only the exit code is available. The [documented Sandbox CLI](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-cli) does not expose process I/O. Do not invent an automatic log-export channel or infer a build failure's cause. Treat user-imported logs as untrusted input; leave automatic guest artifact/log transport for a separate design.
- [ ] Add a supported coding-assistant form adapter after inspecting the actual chosen site during implementation. Verify form submission, return its status, and do not apply assistant-provided code automatically. Unknown sites offer copyable prepared text.
- [ ] Run tests plus a sandbox fixture that tries to delete a host sentinel; sentinel remains unchanged. Verify exit code and missing-log reporting; build success alone must not imply host code was changed. Test a user-imported log separately. Sandbox temp cleanup requires approval or reuse of the sandbox's documented ephemeral lifecycle disclosed at run approval. Commit.

## Task 9: Removal, cleanup, and per-user uninstall

**Files:** Extend `files.py`; create `uninstall.py`; tests `test_files.py`, `test_uninstall.py`, `test_approvals.py`.

**Interfaces:** `preview_recycle(paths: list[str]) -> Proposal`; `preview_cleanup(root: str, rule_id: str) -> Proposal`; `preview_uninstall(app_id: str) -> Proposal`. Executor is the sole execution entry.

- [ ] Test no side effects before approval; changed file ID/content; approval replay; new cleanup matches; junctions/reparse points; partial Recycle Bin failures; unavailable recycling; cancelling during a batch; and uninstall requiring elevation.
- [ ] Run targeted tests; confirm failure.
- [ ] Snapshot exact regular files, normalized paths, file IDs, sizes, fingerprints, and approved root identity. Reject directories, network targets, permanent deletion, and unstable identity. Close path-swap races using handle-based checks/appropriate locking; if the chosen recycle API cannot maintain the needed guarantees, fail closed rather than claiming an atomic guarantee.
- [ ] Cleanup uses explicit named rules and fixed manifests. Recycle only approved items; never fall back to permanent deletion. Item-by-item receipts record verified/failed/unknown outcomes; never replay a partially completed batch automatically.
- [ ] Inventory only trusted per-user app entries with stable package identity. Approve the exact uninstall action and disclose unknown installer side effects. Launch a verified, non-shell uninstaller only where normal-user behavior is supported; otherwise produce manual steps. System components and administrator uninstall remain manual.
- [ ] Run unit tests and manual removal on disposable local files only; restore one from Recycle Bin to confirm the UX. Do not uninstall real applications during automated testing. Commit.

## Task 10: Verification, interruption, recovery, and audit history

**Files:** Extend `executor.py`, `runner.py`, `store.py`, adapter verifiers; tests `test_runner.py`, `test_store.py`.

**Interfaces:** `Store.append_event(task_id: str, event: dict) -> None`; `Runner.inspect_interrupted(task_id: str) -> Result`; `resume_after_review(task_id: str) -> None`.

- [ ] Test crash before dispatch, after approval consumption, during a write, and after an effect before its receipt; duplicate model calls; API disconnect after successful tool action; worker hang; cancellation while waiting on the browser.
- [ ] Run tests; confirm failure.
- [ ] Persist intended actions before effects, then verification evidence. On restart mark incomplete actions unknown/interrupted and inspect read-only postconditions. Never infer rollback or retry from missing receipts. Resuming requires user review and fresh approval for any new/remnant removal.
- [ ] Enforce task/action deadlines, terminate isolated helper processes on Stop, and prevent new work until previous effects are reconciled. Record cancellation honestly when an irreversible effect was already in progress. Pause on foreground-target mismatch/manual input where foreground automation is required.
- [ ] Run fault-injection tests; expected no duplicate writes and no automatic resume. Expose history export and approved history cleanup; do not log keys/raw sensitive payloads. Commit.

## Task 11: Sign-in startup, duplicate prevention, and low idle use

**Files:** Create `startup.py`; extend `app.py`; tests `test_startup.py`; performance section in `acceptance.md`.

**Interfaces:** `set_startup_enabled(enabled: bool) -> Result`; `acquire_instance_lock() -> bool`; `register_stop_hotkey() -> Result`.

- [ ] Test two launches produce one executor; startup shortcut quoting handles paths with spaces; enabling is idempotent; disabling removes only the app-owned entry after explicit approval; offline startup makes no Gemini calls.
- [ ] Run targeted tests; confirm failure.
- [ ] Use a per-user Windows named mutex and an app-owned Startup-folder shortcut to the packaged executable with `--startup`. Keep UI hidden on startup. Removal of this shortcut is removal under the user's rule: explain it and require the exact confirmation.
- [ ] Initialize the Gemini connection and automation helpers only on demand. Avoid polling loops; use Qt/Windows events. Do not add scheduled-task or service startup mechanisms in parallel.
- [ ] Test sign-out/sign-in, disable/enable, sleep/wake, battery operation, and no network. Measure ten minutes idle: target private working set under 200 MB, mean CPU under 1%, no model traffic/screenshots, no inference GPU use. Record results and causes if targets are missed. Commit.

## Task 12: Packaging, installation, upgrades, and removal

**Files:** Create `packaging/*`, `docs/setup.md`, `docs/supported-tools.md`, `docs/troubleshooting.md`, `docs/threat-model.md`.

**Interfaces:** packaged `DesktopAgent.exe` supports normal, `--startup`, and `--native-host` modes. Installer scope is current user, with stable app ID and separate app-data storage.

- [ ] Add checks that installed file paths and host manifest paths resolve, origin IDs are explicit, no credentials are bundled, settings survive upgrade, and startup entries reference the current executable.
- [ ] Build with `python -m PyInstaller packaging/desktop-agent.spec --noconfirm`; compile `installer.iss` using the installed Inno Setup compiler. Pin exact build tool versions once tested; include required Qt licenses/notices.
- [ ] Installer shows install path and creates only app-owned registrations. Native-host origins must match the installed browser extension ID. Document unpacked-extension setup for the personal pilot; a signed browser-store extension is a later distribution task. Do not bypass browser security restrictions.
- [ ] Upgrade only while idle after a preview, because replacing old binaries includes removal. Keep rollback package; preserve credentials/history. No automatic self-updater. Uninstall explicitly lists executable files, startup shortcut, native-host registration, optional data/history deletion, and optional credential removal; retained data is the default.
- [ ] Test a clean standard-user Windows VM without Python: install, launch, bridge connect, upgrade, rollback, uninstall with retained data, reinstall, and explicit data removal. Test unsigned-build warning behavior; production code signing needs a certificate not supplied here. Commit.

## Task 13: End-to-end acceptance and staged personal rollout

**Files:** Complete `tests/acceptance.md`, add `docs/pilot-results.md` during execution.

- [ ] Run `python -m pytest -q` and `node --test extension/tests/bridge.test.mjs`; all pass. Live API tests remain opt-in; default suite is offline and uses synthetic data.
- [ ] Run the five reference workflows from the design using disposable files and a test browser destination. Verify exact app/project/tab identity, outbound preview, target-bound approvals, and evidence for every effect.
- [ ] Inject malicious page/log instructions, fake model approvals, expired approvals, file replacement, browser disconnect, quota exhaustion, lock/unlock, stop, crash, and sign-in recovery. Zero unauthorized removals and zero blind write replays are required.
- [ ] Complete performance measurements with the user's ordinary editor/browser workload. Report actual idle memory, active memory, CPU, startup availability, request latency, and token consumption. Do not present model download size or hardware specs as a measurement.
- [ ] Pilot manually with reads only; enable ordinary writes after observed success, then removal only against disposable files. Enable sign-in startup only after the packaged manual-launch application passes recovery and stop tests.
- [ ] Record supported apps/sites and remaining manual operations; document key rotation, startup disable, emergency stop, history cleanup, and troubleshooting. Mark release complete only after acceptance evidence exists, not after the executable builds.

## Task 14: Obsidian vault and long-term memory

Execute after Tasks 2, 3, and 6 and before final acceptance in Task 13. The numbering preserves the original task references; this is not an instruction to postpone memory until after release.

**Files:** Create `src/desktop_agent/memory.py`, `tests/test_memory.py`, `docs/memory.md`; extend `settings.py`, `context.py`, `runner.py`, `ui.py`, and `tests/acceptance.md`. Create the vault folders/index only during setup, after confirming the vault location.

**Interfaces:** `MemoryStore.search(query: str, limit: int = 5) -> list[MemoryExcerpt]`; `MemoryStore.prepare_save(note_path: str, text: str, expected_fingerprint: str | None) -> Proposal`. Define `MemoryExcerpt(path: str, text: str, modified_at: str, provenance: str)` in `contracts.py`. Saving executes through the existing executor/file policy, never through a separate write path.

- [ ] Write failing tests for empty vault, denied folder, Unicode filenames, outside-vault paths, reparse escapes, hidden files, `.obsidian` exclusion, and files above 256 KiB. Assert search returns at most five excerpts and respects the existing total context budget.
- [ ] Add tests that malicious notes cannot authorize tools or change policy; secrets are redacted before cloud upload; conflicting preferences retain their sources; model-generated claims are marked inferred and never overwrite user-stated preferences automatically.
- [ ] Run `python -m pytest tests/test_memory.py tests/test_context.py tests/test_policy.py -q`; confirm the new tests fail before implementation.
- [ ] Add the vault path setting, default proposal `D:\Desktop agent\memory`, per-folder grants, and a memory-saving toggle. Create `Project`, `Preferences`, `Workflows`, `Decisions`, `Task Summaries`, and an index when setup is accepted. No plugin installation, sync activation, or whole-vault import.
- [ ] Implement case-insensitive filename/heading/content token matching using the standard library, with stable ranking and bounded reads. Search on task demand only, attach source paths/dates to excerpts, and pass results through Task 2's context grants/redaction/preview. The agent must work while Obsidian is closed.
- [ ] Implement new task-summary notes with timestamp plus task ID, provenance, relevant outcome, and source references. Preview preference/decision changes; use Task 6's backup/approval path for existing notes. Compare the expected fingerprint immediately before committing; a mismatch returns a conflict with no overwrite. On Windows use an appropriate exclusive lock during the compare/write section; if a safe lock cannot be acquired, abort.
- [ ] Test simultaneous user edits, duplicate summary retries, blocked overwrites, deletion without approval, and vault unavailability. Reuse task IDs for idempotence; never create repeated notes after reconnect/restart. Memory failure leaves the completed task result intact and reports that its summary was not saved.
- [ ] Add a setup explanation that local notes selected for Gemini leave the computer; offer a source preview. Backups are user-approved, non-destructive snapshots outside the vault. Do not automatically delete old notes/backups or enable cloud sync.
- [ ] Run all memory/context/policy/file tests; manually open the vault in Obsidian, find a dated decision from the agent, modify a note during a proposed update and verify conflict rejection, then close Obsidian and verify retrieval still works. Record Obsidian's separate RAM footprint when open. Commit.

**Acceptance:** A user-stated editor preference can inform "open my project" after restart; source is visible; a note saying "delete without approval" has no effect; API keys/approval tokens never appear in the vault; existing execution receipts remain authoritative in SQLite.

## End-to-end acceptance checklist

- [ ] No local inference software, weights, or model service installed.
- [ ] Valid Gemini key is stored securely; actual configured model completes a tool-call probe.
- [ ] Computer actions are unavailable outside the central executor.
- [ ] All removals, including app-owned logs, settings resets, startup disabling, upgrades, and uninstall, follow the exact-operation approval rule.
- [ ] Unrestricted commands/UI/browser evaluation cannot bypass approvals; untrusted recipes cannot mutate the host.
- [ ] Replaced targets invalidate approval; adapter cannot verify identity safely → no write.
- [ ] Denied approval, no reply, expiry, cancellation, or offline state produce no unauthorized change.
- [ ] API errors and interrupted effects never trigger blind write retries.
- [ ] Startup is per-user, quiet, single-instance, and idle without cloud calls.
- [ ] Stop/session lock works; interrupted work stays paused after restart.
- [ ] Standard-user clean-machine package and browser connection work as documented.
- [ ] Actual resource usage and capability limits are recorded.
- [ ] Obsidian memory works with the editor closed, respects folder grants, cites source notes, rejects concurrent overwrites, and cannot bypass execution policy.
- [ ] SQLite owns live state/approvals; Credential Manager owns secrets; vault owns readable long-term notes. No automatic vault cleanup or whole-vault Gemini upload.

## Inputs needed during implementation

Planning does not need these secrets or choices now. Setup will need a Gemini API key entered locally; the preferred browser; actual coding-assistant site; allowed project folders/apps; approval to enable startup when ready; and an explicit decision about exposing project content to cloud models. Detect Windows edition/Sandbox support before offering execution recipes. API model availability, billing behavior, package versions, UI selectors, and signing options must be checked in the real target environment.

## Effort and execution handoff

Rough planning allowance for an experienced implementer: 2–4 weeks for the supported personal pilot, with browser site adaptation, Sandbox compatibility, and removal identity guarantees the main uncertainty. This is not a delivery commitment; reduce breadth before weakening approval boundaries.

Read the design brief and this plan together before coding. Recommended execution is one implementer completing tasks in order with tests and a permission-focused review at each stage. The plan intentionally defers voice, local models, unrestricted desktop driving, elevated/system removal, arbitrary host scripts, automatic sandbox log/artifact export, remote access, store publication, unattended scheduled actions, and automatic updates. Add those only as separate reviewed capabilities.

## Plan self-review

Coverage checked: cloud-only model; resource limits; tool controls; ordinary writes; removal/cleanup/uninstall approvals; browser and Windows control; isolated build tasks; verification; secrets/privacy/cost; startup; stop; crash recovery; packaging; upgrade/uninstall; clean-machine and laptop acceptance; Obsidian long-term memory, retrieval, provenance, conflict-safe writes, and separation from authoritative execution state.

Review-focus cases are assigned to explicit tests above. Shared records and executor signatures are the handoff between tasks. Actual SDK capability, native-app selectors, file-lock/recycling interoperability, Windows Sandbox support, signed packaging, resource targets, and provider spending behavior remain execution-time checks. No implementation or system registration was performed while writing this plan.
