# Desktop Pilot terminal voice agent

Status: design direction approved in chat; written specification awaiting review.
Date: 19 October 2026.

## Outcome and scope

The user wants a personal Windows assistant operated from PowerShell, with continuous voice conversation until explicitly stopped, spoken responses, and visible activity for every API request and error. Configuration belongs in the local development environment. The terminal becomes the default interface; no browser page, HTTP listener or FastAPI server is needed. Existing desktop and browser capability milestones remain part of the overall project, but this milestone delivers the terminal and voice subsystem rather than claiming the entire assistant is complete.

This specification supersedes the original design's voice deferral and native-window-first interface. It preserves the central executor, exact-operation approvals, cloud-only inference, private Obsidian memory and SQLite receipts. Existing GUI files remain available through an explicit GUI option; they are not deleted.

## Approaches and decision

1. Direct Gemini Live audio, recommended and approved in principle: stream audio and receive speech on one persistent connection. Avoid a separate transcription → planning → speech-generation pipeline for ordinary conversation.
2. Separate speech recognition, existing text runner and speech generation: reuses more runner code but introduces multiple sequential requests and different cancellation behavior. Do not introduce this as a parallel implementation.
3. Browser voice frontend: adds a server and browser lifecycle and conflicts with the requested terminal experience. Excluded.

## Launch and configuration

`python -m desktop_agent` launches the interactive terminal. `--text` selects typed interaction without opening audio devices; `--gui` explicitly opens the retained native preview. `--status` remains offline and compatible. `--list-audio-devices` lists local microphone/speaker identifiers without connecting to Gemini.

Credentials retain process `GEMINI_API_KEY` → ignored project `.env` → Credential Manager precedence. Never execute or expand environment-file content. Extend the existing bounded literal parser only for explicit nonsecret voice configuration: `GEMINI_LIVE_MODEL`, `VOICE_INPUT_DEVICE`, `VOICE_OUTPUT_DEVICE`. Process values override file values; absent values use validated defaults. Preserve unrelated existing file contents and never log credentials. Do not require activation of the virtual environment.

Propose `gemini-3.8-live` as the configurable Live model based on the official capabilities guide checked on this date. Verify installed SDK compatibility before relying on fields and do not silently fall back to another model. Account availability is established only by an explicitly started session. Keep the existing text model setting independent.

Launch displays the destination, chosen model, audio devices and continuous-microphone disclosure. Only an explicit terminal Start/Enter connects and opens capture. Starting the program alone does not transmit audio or make a billed probe. The user can change devices before Start.

## Terminal interaction and observability

Show current state, elapsed session time, connection identifier and last activity. Append timestamped events for connect start/success/failure, user-turn boundaries, first response, tool request/result, returned usage, interruption, pause and shutdown. A single refreshed status line provides activity between events; redirected output becomes plain append-only lines with no terminal control sequences. Do not clear error history or restart the process for each update.

Controls are `/start`, `/stop`, `/pause`, `/resume`, `/text <request>`, `/memory <query>`, `/help`, `/quit`, and Ctrl+C. Commands must remain responsive while audio is active. `/stop` ends capture, playback and the network session; `/pause` additionally cancels pending task work and invalidates approvals. `/resume` returns to ready but does not reconnect or replay interrupted actions; `/start` explicitly begins a fresh session. Ctrl+C performs the Stop/Exit cleanup path. End of terminal input also stops cleanly.

Print sanitized error category, component and next step for every failed operation, including audio-device errors, configuration, credentials, network, quota, SDK decoding, tool validation and journal failures. Never print raw provider payloads, audio frames, secrets or exception representations that could contain credentials. Internal failures expose a safe diagnostic location/category and sanitized call-site information. Avoid SDK/HTTP debug logging. Raw audio and transcripts are not persisted; display redacted transcripts in the terminal only. Strip terminal escape/control sequences from untrusted model text and source paths.

For Live, distinguish one session connection, streamed turns, tool calls and returned usage; do not count every audio frame as a separate billed API request. Aggregate chunk counts/bytes periodically rather than printing every frame. For existing text requests show each actual attempt and duration. Unknown usage/cost stays unknown rather than zero.

## Audio and connection architecture

Use the installed official Google GenAI async client and one Windows audio dependency selected after wheel/device compatibility verification. Prefer an available PortAudio-based wheel; no local model or external audio service. One asyncio coordinator owns connection state; microphone capture and speaker playback must not block reception or terminal controls. Bounded queues hold at most 250 ms of input and 500 ms of output. Overflow stops the turn/session with a visible error rather than allowing stale commands to accumulate.

Start with mono signed 16-bit little-endian PCM, 16 kHz capture and 24 kHz playback as documented. Validate actual device support at startup; fail with device guidance if unsupported rather than silently changing format. Send approximately 20–40 ms microphone chunks. Play response chunks immediately rather than buffering a full sentence. Keep only bounded in-memory audio buffers and release device handles on every exit path.

Use provider voice activity detection for conversation turn boundaries. On provider interruption, stop speaker playback immediately and discard queued output from the interrupted turn. Process all parts of each server event, including audio, transcript, usage, cancellation and tool requests. Serialize tool execution independently of the event-receiving loop. Retain provider tool call identifiers and reject duplicate execution.

A headset is the first acceptance setup: acoustic echo cancellation is not assumed from raw audio capture. Speakerphone echo handling is a separate measured requirement before claiming reliable full-duplex speaker operation. Do not install drivers or change system audio settings automatically.

Disconnect, session expiry, device loss or protocol failure closes the connection and all audio streams, marks affected work interrupted/unknown as appropriate and returns to stopped. Show how to start again. No automatic reconnection, hidden retry or write replay in the first voice milestone. Send no screenshots or system audio.

## Permissions, approvals and memory

All Live tool calls pass the existing schema validation, capability registry, approval manager and executor. Model-generated words or microphone transcripts cannot approve operations. Begin with the currently registered constant read-only `runtime_status`; unknown tools receive a denied result. Adding voice does not unlock unrestricted commands or generic desktop clicks.

Each completed spoken user turn/tool-bearing interaction gets a local task identity before any tool effect. Bound tool actions to 20 per interaction and one executing task at a time. If a tool call arrives without an attributable task/turn identity, reject it. Persist call claims before dispatch, retain verification receipts and never announce an effect based solely on spoken model output. Label ordinary replies as model advice; terminal receipts are authoritative.

For future non-read tools, stop audio capture/playback and close the Live session before presenting the exact local approval prompt, so approval text is not uploaded. Only exact typed confirmation bound to that proposal can authorize it. Denial, expiry, lock, Stop or journal failure rejects the operation. Execute and verify through the central executor; a new voice session requires explicit Start. This milestone must not invent a second write path or bypass the existing runner's non-read pause behavior.

Local memory search reuses the granted, bounded read-only store. Show sources locally. Attaching excerpts requires an explicit terminal preview and consent before transmission, and starts a fresh session with the selected bounded context. Neither voice sessions nor logs automatically import the vault or write conversation notes. Preferences in notes remain untrusted data.

## Safety lifecycle and resource limits

Retain one per-user instance lock across terminal and GUI modes. Terminal mode owns a minimal Windows message pump or hidden native receiver for the existing emergency hotkey and session notifications; it does not show the GUI. If session monitoring cannot initialize, voice/cloud execution stays disabled. Hotkey conflicts show visible fallback controls.

Ctrl+Alt+Pause and lock/disconnect notifications immediately signal cancellation, close capture/playback, stop the Live connection, invalidate approvals and leave the app paused. Unlock never resumes capture or work. A failed approval invalidation blocks Resume until the journal succeeds. Native callbacks enqueue coordinator work rather than waiting for network or database operations in the OS event handler. Release registrations, handles and the instance lock in final cleanup.

Cap each voice session at ten minutes, twenty completed turns and twenty tool calls per turn. Warn before the time limit and end without automatic restart. Bound connection establishment to 15 seconds and shutdown to 5 seconds, with visible incomplete-cleanup reporting. Display elapsed streaming time and returned usage. A configured dollar estimate cap with unavailable Live rates/usage must disable Live rather than imply protection; text mode remains usable under its existing budget rules. These are application limits, not provider billing guarantees.

## Speed and acceptance

Optimize with one persistent connection during an explicitly active session, concurrent capture/receive/playback, small bounded buffers, immediate streamed output, no per-frame disk logs and no repeated vault search or second model request for casual speech. Avoid model escalation for Live and do not remove safety checks to reduce latency.

Measure connection time, end-of-speech to first audio played, interruption-to-playback-stop and Stop-to-microphone-close with monotonic clocks. Target under 1.5 seconds median response onset on the user's network, under 200 ms playback interruption and under 500 ms local capture stop. These are acceptance targets, not claims; separately report provider/network time and local queue time. Idle before Start and after Stop must produce no cloud traffic or audio capture.

Offline tests use fake audio and fake SDK sessions. Cover default CLI/no GUI, environment precedence and secret-safe diagnostics, bounded queues, combined server parts, duplicate/unknown tool calls, interruption flushing, session limits, disconnect, Ctrl+C, invalidation failure, lock/unlock, denied memory consent and cleanup. Confirm text-mode compatibility and the existing suite. Real SDK schema/transport tests must not require an account.

Manual acceptance requires local user-started microphone capture, a configured account, headset conversation, overlapping speech, Stop, unplugged device, network loss and actual emergency-stop/lock delivery. Confirm no recording files or credential logs are created. Record real latency and usage. Do not claim voice complete or the broader desktop assistant complete until the corresponding evidence is recorded.

## Delivery order and remaining project

1. Terminal launcher, safe activity events and typed runner integration.
2. Validated voice environment settings, device inspection and streaming session with fake-session coverage.
3. Continuous conversation, interruption, session limits and executor receipts.
4. Terminal-native emergency stop/session lifecycle and explicit memory attachment.
5. Live acceptance and measured fixes; update run instructions and supported capabilities.
6. Continue original file/app/browser workflows, verification, packaging and final acceptance as separate tested milestones. Do not mark those complete because voice works.

Work directly on main and push each coherent verified milestone per the user's existing instruction. Keep local .env, vault, audio and runtime data ignored. No automatic startup activation, removals or production release is included in this design approval.

## Sources checked

- https://ai.google.dev/gemini-api/docs/live-api — streaming protocol, PCM formats, interruption and transcription.
- https://ai.google.dev/gemini-api/docs/live-api/capabilities — current Live models, all-parts event processing and session configuration. Model/SDK/account compatibility must be verified again during implementation.

## Self-review

The design preserves the user-selected continuous conversation mode and terminal-only default; it distinguishes live streaming consent from sensitive-context consent and local operation approval. It defines fallback behavior without silent model substitution, bounded buffers and failure cleanup, safe logs and acceptance evidence. Voice changes the interaction layer; existing pending desktop/browser capabilities remain explicitly pending.
