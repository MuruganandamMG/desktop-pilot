# Desktop Pilot

A Windows assistant using cloud Gemini, local tools, and Obsidian memory. Removal operations require explicit, operation-specific user approval.

**Status:** default launch is now a terminal voice agent: continuous microphone conversation, streamed spoken replies, safe API/error logs and keyboard Stop controls. No browser or visible window opens. The legacy read-only GUI is available only with `--gui`. Voice does not execute computer actions. Live account access, headset audio and response latency still require a user-started test. See [setup](docs/setup.md) and [implementation status](docs/implementation-status.md).

```powershell
cd "D:\Desktop agent"
.\.venv\Scripts\python.exe -m desktop_agent
```

Close any older Desktop Pilot window first. Press **Enter** to start voice, **S** to stop, **Q** to quit. Set your key in the ignored local `.env`; never paste it into chat.

- [Implementation plan](docs/superpowers/plans/2026-10-19-windows-agent-implementation.md)
- [Design and safety boundaries](docs/superpowers/specs/2026-10-19-windows-agent-design.md)
- [Contributor and agent instructions](AGENTS.md)

The private `memory/` vault is excluded from Git. Never add API keys or personal notes to this repository.
