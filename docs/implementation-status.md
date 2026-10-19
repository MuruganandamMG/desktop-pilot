# Implementation status

Started 19 October 2026. The user authorized vault configuration, repository setup, feature-branch commits/pushes, and implementation of the existing plan.

## Current work

- Repository bootstrap: complete; origin connected and initial main commit pushed.
- Local Obsidian vault: configured at the authorized path with private notes and local vault registration; excluded from Git. Registration and real local note retrieval verified; Obsidian editor rendering still to check.
- Task 1: immutable validated actions, persisted task transitions, interrupted-task recovery and a manual-launch native window implemented. The later cloud preview records actual request states; raw prompts are not persisted.
- CI: Windows Python 3.12 checks run on pushes and pull requests; foundation milestone 30fd7cc passed hosted run 39274445407. Later commits are checked separately.
- Task 2 foundation: validated nonsecret settings, credential-store adapter, bounded source grants and best-effort redaction implemented and offline-tested. Cloud payload preview is tested/rendered using synthetic data. Actual Credential Manager write and account access require local user key entry; no Gemini credential was present on inspection.
- Task 3 core: deny-by-default capability registry, immutable preview digests, five-minute single-use approvals, target revalidation, cancellation checks and persistent duplicate-action protection implemented. Tests exercise fake/missing/replayed/expired/changed approvals and blocked capabilities; real adapters and approval UI still pending.
- Task 5 partial: cancel-default cloud consent, masked local key entry, model probe, async cloud worker with its own SQLite connection, request cancellation, close cancellation and native instance lock implemented. Actual API calls occur only after user consent. No tray, global stop hotkey, session-lock handler or writable desktop adapters yet.
- Task 14 partial: bounded granted-folder search with source dates/provenance and optional user-selected excerpts in the cloud preview implemented. No automatic note writing, pruning or whole-vault upload.
- Task 4 core: official google-genai 2.31.0 client and bounded tool loop implemented with manual dispatch, preserved provider content/signatures and call IDs, safe errors, actual-request retry accounting, deadline/cancellation, token-usage receipts, estimated per-task budgets, and an opt-in capability probe. SDK continuations are disabled. Capped tasks allow one attempt per request; unknown cost blocks new requests. Non-read batches stop for local review; tool observations are not uploaded unless explicitly classified as safe constant runtime metadata. Explicitly selected escalation is limited to invalid reasoning before tools; probes never escalate and report the selected model ID. Real SDK behavior is exercised via offline HTTP transports; live account/model access is not inferred from these tests.
- Current offline suite: 82 passing tests, one symlink test skipped because this standard-user host cannot create symlinks. Only constant `runtime_status` is registered; no destructive capability is exposed. Windows native launch/clean exit and offscreen cloud window/consent rendering verified. Cloud consent and worker flows use fake clients in tests; actual account/model probe awaits local key setup.
- Task 4 live validation, Tasks 6–13 and remaining portions of Tasks 2, 3, 5, 14 are pending. No startup activation or automatic computer control is enabled.

## Execution decisions

- Interpret "wallet" as the Obsidian vault from the preceding discussion. No financial wallet is created.
- Interpret "remote access" as the GitHub Git remote. No remote desktop access is enabled.
- Native execution with the executing-plans, test-driven-development, verification-before-completion, and Ponytail skills. This is a new repository, so bootstrap precedes branch isolation.
- The existing user-authorized vault path is `D:\Desktop agent\memory`. Do not import personal vaults or enable sync/plugins.
- Push each coherent tested commit to a feature branch. Do not merge to main automatically.
- Ruling: keep the per-plan skill scratch ledger private and the durable implementation status public; PowerShell-native task bookkeeping replaces the skill's Bash helper scripts on this Windows host. Cost: ledger operations are verified manually.
- Ruling: depend on PySide6-Essentials, not the full PySide6 distribution, because this native window needs QtWidgets and no embedded browser/PDF engine. Cost: add a module explicitly if a later feature actually needs it.
- Ruling: implement read-only vault search before file-write adapters; defer memory saving until the file permission/locking foundation exists. Cost: memory is manually maintained in this milestone.
- Ruling: Windows drive roots/AppData may be hidden, so allow hidden ancestors of the explicitly selected vault while continuing to reject reparse ancestors and hidden vault contents. Cost: hidden parent directories are not themselves a permission boundary.
- Ruling: cost caps are per-task estimates based on dated user-supplied rates. Missing usage or possibly billed failed attempts make cost unknown, and a configured cap then blocks further requests. Cost: provider billing can exceed the estimate, including the last in-flight request; this is not a provider-side hard spending cap.
- Ruling: stronger-model escalation is allowed only before any tool executes and only to an explicitly configured ID; no implicit latest-model alias. Cost: failed reasoning after verified reads pauses instead of trying a new model with possibly incompatible opaque signatures.

## Independent milestone review

A read-only reviewer reproduced the suite and found three P2 issues. Each was fixed with a failing regression followed by the passing suite: quoted JSON/YAML-style credential redaction; matched text outside the initial 12,000-character excerpt; and executor receipts omitting summaries/verification evidence. Receipts now retain bounded allowlisted metadata while excluding raw output fields. Author tests after the fixes: 37 passed, one skipped.

Live credentials, junction replacement races, physical keyboard/accessibility checks, and future adapters were not certified by this review. No hosted branch-protection rule or automatic merge has been enabled. The private vault and settings are not published.

## Gemini milestone review

An independent read-only review reproduced 76 passing tests and one skip, then identified four P2 issues. All were reproduced with failing regressions and fixed: caps now prevent internal retries on potentially unknown charges; SDK decoding errors retain request-attempt counts and stop without exposing payloads; a probe cannot silently certify an escalation model; tool-use prompt tokens are included in usage/estimates. An additional real-SDK regression found automatic continuations making uncounted requests, now explicitly disabled. Provider blocks are kept distinct from invalid reasoning so they do not trigger escalation. Final local suite: 82 passed, one skip.

No API key is stored, so live auth, model availability, provider billing, real credential writes and physical accessibility remain unverified. The application is ready for a locally entered key and an explicitly consented probe; no key is requested in chat or the repository.

## Pending live prerequisites

Gemini key and capability probe; browser/site selection; actual desktop interaction; startup opt-in after acceptance; clean-machine packaging/performance checks. None is treated as complete merely because offline tests pass.
