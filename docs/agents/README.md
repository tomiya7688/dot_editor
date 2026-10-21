# Context router: Claude Code and Codex

The root `AGENTS.md` and `CLAUDE.md` share one policy. **Do not load all linked documents by default.** The router is for internal contributors only, not product users.

## Read first

1. Identify this Issue's goal, acceptance criteria, owned files and current base/branch. Inspect `git status`, changed paths, and relevant PR feedback before editing.
2. **Search first, read second:** `rg --files`, focused `rg -n`, and `git diff --name-only origin/main...HEAD` are initial candidates. If source and tests are already known, read those directly. Otherwise use the [task-to-source/test map](task-map.md) *only to locate candidates*.
3. Read the selected source, related tests and the needed part of its authoritative specification. Do not infer semantics from the index or a search snippet alone.

## Normally exclude

Build outputs (`dist/`, `build/`, `rust/target/`), `.venv/`, generated indexes, stale logs, unrelated Issues, entire histories and unrelated docs. **Exception:** read any of these when directly relevant (such as release artifact verification).

## Scope and stop conditions

Stop expanding the search once the behavior, source, relevant tests, invariants and acceptance checks are established. Expand for a failing test, shared public API/JSON change, unclear ownership, or a discovered caller. Run targeted local checks first, but never omit required CI or affected E2E. Report **actual** commands, files reviewed, unknowns and unverified outcomes.

## Read when needed

- Applicable parts of [R01–R20](../../コーディング規約.md) and the [development workflow](../../doc/ワークフロー/ワークフロー.md) (all rules remain binding; CI checks remain required)
- Parallel editing, PR ownership or handoff: [collaboration](collaboration.md) with optional Context Pack
- CI, distribution or internal build work: [quality gates](quality-gates.md), [developer reference](development.md)
- Specific cell-refinement regression: [regression specification](../Refinement_regressions.md)

The route map is a discovery aid. Specialized ObaPick tools should be adopted **only after real repeated tasks justify their maintenance cost**. No context reduction percentage or Claude/Codex load behavior is assumed without measurement.
