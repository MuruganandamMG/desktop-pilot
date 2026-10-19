# Desktop Pilot

A Windows assistant using cloud Gemini, local tools, and Obsidian memory. Removal operations require explicit, operation-specific user approval.

**Status:** read-only cloud preview implemented; this is not yet a system-control application. The native app can store a Gemini key locally, preview a request, test a selected model, ask Gemini, cancel a request, and search local memory. Only the constant runtime-status read tool is enabled. Live model/account access still needs an opt-in test with your key. See [implementation status](docs/implementation-status.md) and [setup](docs/setup.md).

- [Implementation plan](docs/superpowers/plans/2026-10-19-windows-agent-implementation.md)
- [Design and safety boundaries](docs/superpowers/specs/2026-10-19-windows-agent-design.md)
- [Contributor and agent instructions](AGENTS.md)

The private `memory/` vault is excluded from Git. Never add API keys or personal notes to this repository.
