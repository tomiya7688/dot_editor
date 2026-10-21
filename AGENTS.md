# Agent entrypoint: Claude Code and Codex

This is for repository contributors, **never user-facing documentation**.

- One Issue per branch/PR; do not overwrite another agent's work or push to `main`. See [collaboration rules](docs/agents/collaboration.md).
- Rust Core is the product authority. Preserve Python 3.10–3.14 build/test support, JSON compatibility and retained detail.
- Apply [R01–R20](コーディング規約.md) and the [development workflow](doc/ワークフロー/ワークフロー.md). No disabled tests, hidden failures or unverified claims.
- Start with the [task-first context router](docs/agents/README.md). Search for relevant source and tests first; read only necessary original evidence. Widen scope when dependencies, failures or acceptance criteria require it.
- Report changes, exact validation, uncertainty and handoff in the PR. Keep agent procedures out of user README, help and public API guides.
