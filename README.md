# Desktop Pilot

A Windows assistant using cloud Gemini, local tools, and Obsidian memory. Removal operations require explicit, operation-specific user approval.

**Status:** default launch is a hands-free voice agent: it starts listening, streams spoken replies, and accepts local spoken pause/resume/exit commands. The terminal shows API/error logs; no browser or visible window opens. The legacy read-only GUI is available only with `--gui`. Voice does not execute computer actions. Real microphone sharing, account access and latency still require live acceptance. See [setup](docs/setup.md) and [implementation status](docs/implementation-status.md).

```powershell
cd "D:\Desktop agent"
.\.venv\Scripts\python.exe -m desktop_agent
```

Close any older Desktop Pilot window first. Launch and speak normally; no Enter-to-start is required. Say **Pilot pause**, **Pilot resume**, or **Pilot exit**. Use a headset and the Windows default microphone. Set your key in the ignored local `.env`; never paste it into chat. While paused, Windows still listens locally for commands; microphone questions are not sent to Google.

- [Implementation plan](docs/superpowers/plans/2026-10-19-windows-agent-implementation.md)
- [Design and safety boundaries](docs/superpowers/specs/2026-10-19-windows-agent-design.md)
- [Contributor and agent instructions](AGENTS.md)

The private `memory/` vault is excluded from Git. Never add API keys or personal notes to this repository.
