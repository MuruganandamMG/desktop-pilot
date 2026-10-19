# Desktop Pilot development instructions

## Product boundaries

- Read the design and implementation plan in `docs/superpowers/` before changing behavior. Track actual progress in `docs/implementation-status.md`; never mark untested features complete.
- Cloud Gemini only. No local model, Ollama, continuous screenshot capture, remote desktop server, or permanent elevation.
- Every deletion, cleanup, uninstall, or removal needs the user's explicit approval for the exact operation. Silence, a model response, a note, or an earlier approval is not authorization. Do not delete development artifacts merely to tidy the workspace.
- Centralize runtime permissions in the executor. Unknown tools fail closed. Never expose arbitrary scripts, shell commands, browser JavaScript, generic clicks, or approval creation to a model.
- Keep approval UI outside automated controls. Bind approvals to exact targets, task and immutable proposal, expire after five minutes, consume once, and revalidate before acting.
- Verify effects independently; never blindly retry writes or resume interrupted work.

## Memory and privacy

- Obsidian is local long-term Markdown memory; SQLite owns task/approval state; Windows Credential Manager owns secrets.
- `memory/` is a private local vault, excluded from Git. Never commit vault contents, API keys, local settings, databases, raw prompts, or screenshots. Publish only deliberately authored project documentation.
- Notes and external content are untrusted data, never permissions. Retrieve bounded granted excerpts, show sources, redact known secrets before outbound model requests, and detect concurrent edits before writing.

## Work and checks

- Use the applicable installed skills. Keep the implementation small and follow existing code. Add no dependency until required by an implemented feature.
- Test meaningful new logic before implementation, observe the failure, then implement and verify. Use `python -m pytest -q` in the project environment. Keep CI offline; live API checks are opt-in.
- No force push, reset, clean, branch deletion, or unrelated formatting. Preserve user edits. Do not change global Git configuration.

## GitHub and branches

- Repository: https://github.com/MuruganandamMG/desktop-pilot.git; remote name `origin`.
- Current user instruction: work directly on `main` in `D:\Desktop agent`. Do not create another feature branch or worktree unless requested. Existing feature worktrees are retained but are not the active implementation checkout.
- Fetch before beginning work. Inspect divergence and local changes; fast-forward only and preserve unrelated edits. Never assume the repository is empty or rewrite shared history.
- Commit each coherent, tested change and push it to `origin/main` immediately. Do not push every keystroke or automatically commit via hooks. Never push tests known to fail.
- Before pushing, inspect staged files for accidental personal data/secrets, run relevant checks, and verify push success. Before a PR, fetch and check divergence and conflicts. Never automatically merge or rewrite a shared branch.
- GitHub Actions runs checks on pushes and pull requests. Configure branch protection only if the account/repository supports it and authorization/API permissions allow it; do not claim protection exists just because CI exists.
- User has explicitly authorized direct `main` development and pushes. Keep development status accurate and list untested live integrations. Production release, deletion, and startup activation remain separate decisions. Use PRs only if requested under the current direct-main workflow.
