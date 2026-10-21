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

## Enforcement boundary

Any PR altering `AGENTS.md`, `CLAUDE.md`, CI, declaration checker, or tests must be an explicit, separately reviewed policy change. Passing scripts cannot establish semantic correctness. Configure GitHub branch protection/ruleset to require `Agent policy`, `Declaration comments`, `Rust Core`, all `Python 3.10`–`Python 3.14`, `windows-build` checks and one independent code-owner review. Without branch protection, repository YAML **cannot** stop a direct push or a PR that weakens the tests.
