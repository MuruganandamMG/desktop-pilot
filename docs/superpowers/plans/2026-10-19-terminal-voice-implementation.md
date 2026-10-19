# Terminal voice implementation plan

> For agentic workers: use superpowers:executing-plans inline, with one final review.

Goal: default launch is continuous spoken conversation in a terminal, never the old visible GUI.
Architecture: async Gemini Live session, bounded callback audio buffers, local Windows event receiver and terminal controls. Retain the old GUI only through --gui. Reuse literal environment parsing and the per-user lock.
Tech stack: Python, installed google-genai, sounddevice 0.5.6, existing Qt native event support.
Spec: ../specs/2026-10-19-terminal-voice-design.md

## Constraints and review focus

Keep credentials/raw audio out of logs; no automatic capture before Start; stop on lock/disconnect; no model-supplied approvals; no hidden retries. Test queue overflow, interruption, combined event parts, cleanup on failure, and default CLI dispatch. Voice interaction takes precedence over optional typed conversation: terminal keystrokes control listening only.

## Tasks

- [x] Write failing launcher, settings and bounded audio/session tests; run and observe failure.
- [x] Extend settings parser for explicit voice environment names. Add voice model and device validation with secret-safe errors.
- [x] Implement callback PCM buffering, async Live transport, safe terminal event output, interrupt flushing and bounded session lifecycle. No extra conversational text UI.
- [x] Make voice the default launcher, add device listing and explicit legacy --gui, integrate single-instance and hidden native safety receiver. Verify no visible window or cloud traffic before Start.
- [x] Run fake streaming/error/cleanup tests, full suite and offline device inspection. Do not open microphone or make live API requests during automated tests.
- [x] Review, fix findings, document exact launch command and remaining live acceptance. Commit and push tested changes to main.

Ruling: the user's repeated instruction to replace the GUI and build voice is authorization to execute this plan inline; do not ask the same design question again. Full desktop/browser tools remain separate pending milestones. Raw microphone speech cannot be locally redacted before direct audio upload; disclose this at Start.

Live acceptance remains pending; offline device enumeration and no-capture native startup are the checks performed. Reviewer findings were fixed with regression coverage.

## Hands-free revision

The user's correction explicitly authorizes automatic voice start on launch and spoken lifecycle commands. Replace ordinary keystrokes with the installed Windows English grammar recognizer (three exact Pilot commands) plus fixed local status speech, while retaining Ctrl+C for emergencies. Keep cloud conversation independent of the local command channel so spoken resume works without cloud transmission during pause. Include the inspectable PowerShell/.NET helper as package data; follow the host's execution policy without bypass or system changes.

Tests: automatic startup, spoken pause/resume/exit, malformed helper events, no cloud start when a lock arrives during greeting, and all existing cleanup regressions. Run the helper's synthetic-wave self-test, which neither opens microphones nor speaks through speakers. Review lock/resume races, helper subprocess disposal and packaging. Hardware microphone sharing, headset conversation and actual Live access still require live acceptance.
