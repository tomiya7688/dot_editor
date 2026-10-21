# Quality gates

## Automated enforcement

- **Agent policy:** small AGENTS.md, shared CLAUDE import, reachable context docs; PR Issue/Summary/Validation/Risks/Handoff reports; prevent developer workflow references in user README and public API guides; checker unit tests.
- **Declaration comments:** existing R04 syntax audit and changed Python/Rust file gate, never disabled.
- **Rust:** cargo fmt, clippy with warnings denied, tests, debug and release builds, Rust↔Python JSON compatibility.
- **Python:** each of 3.10/3.11/3.12/3.13/3.14 builds wheel+sdist, installs wheel, runs evaluation and regression tests.
- **Windows:** distribution packaging and smoke tests; no claim that headless smoke proves real GUI dialogs work.

## Local quick checks

```bash
python scripts/check_agent_policy.py
python scripts/context_route_benchmark.py --check
python -m unittest discover -s tests -p test_agent_policy.py
python scripts/check_declaration_comments.py
python scripts/check_declaration_comments.py --changed-base origin/main
python scripts/evaluate.py
python -m unittest discover -s tests
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --workspace --all-targets --all-features -- -D warnings
cargo test --manifest-path rust/Cargo.toml --workspace
cargo build --manifest-path rust/Cargo.toml --workspace --release
```

The full Python version matrix is checked in CI, not proven by a local single-version run. Document commands, version, result and skipped E2E in the PR.

## Context-reduction evidence

A small `AGENTS.md` and passing link checks prove only **structure**, not reduced model input or successful agent routing. For representative repeated tasks, compare before/after paths actually read, relevance to the Issue, time spent searching, and the same acceptance/test coverage. Record model input token counts only when the platform provides them; fetched character counts are not token-use measurements. If the evidence is unavailable, label savings **unmeasured**. Remove a route or tool if upkeep exceeds the search it saves.

## Reproducible routing trials (developer-only)

`python scripts/context_route_benchmark.py --check` checks the task-map for three representative changes: Rust project JSON, Python CLI, and GUI keyboard. Every trial has **independently declared required source, tests, and behavior/fixture evidence**. A missing fixture, broken route, duplicated reference, or route without required evidence fails CI. `--json` reports the full file candidates, character counts and UTF-8 bytes. CI stores that report as the `context-route-evidence` artifact.

The comparison is deliberately limited: **baseline = all eligible owned source, tests, public specifications and project JSON fixtures**, while **routed = the complete list of files linked by that task-map row**. Machine selection is not counted as model input. These figures are only full-file input *candidates*, not actual Claude Code/Codex file reads, token usage, elapsed time, correctness of bug fixes, or guaranteed future savings. No arbitrary reduction target justifies dropping required evidence.

### Real agent evaluation (separate from the static CI smoke)

For each of these three tasks, start a read-only investigation from the **same frozen commit** with the same completion/evidence requirements. Run a broad baseline and then the task-first route in separate clean Claude Code and Codex sessions/worktrees. Keep model/version, permissions, tools, cache/context state and prompts comparable; record differences honestly. Do not feed baseline's answers to the routed session. For every trial, record agent, version, base SHA, task, inspected files and ranges, source/test/spec/fixture coverage, checks actually executed, tool-read bytes if available, tool calls, wall-clock time if measured, and genuine platform-provided input tokens **only if available**. Missing measurements are `unknown`, not zero.

Both runs must meet the **same acceptance and mandatory CI/E2E requirements**; a route that missed required evidence, failed validation, or caused rework is not a successful efficiency improvement even if fewer bytes were inspected. Check the original sources rather than trusting the router or agent self-report. Write only a short, sanitized comparison and source/run links into the private developer Issue/PR discussion; do not commit raw agent logs, credentials, personal information or product-user documentation changes. If a real agent cannot run in the available environment, explicitly mark the real-world comparison **unverified**.

## Enforcement boundary

Any PR altering `AGENTS.md`, `CLAUDE.md`, CI, declaration checker, or tests must be an explicit, separately reviewed policy change. Passing scripts cannot establish semantic correctness. Configure GitHub branch protection/ruleset to require `Agent policy`, `Declaration comments`, `Rust Core`, all `Python 3.10`–`Python 3.14`, `windows-build` checks and one independent code-owner review. Without branch protection, repository YAML **cannot** stop a direct push or a PR that weakens the tests.
