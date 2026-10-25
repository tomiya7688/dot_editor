# Task-first context router (contributors only)

Keep `AGENTS.md` short. Read **only task-relevant** sources; this page is an index, not a second rulebook.

## Read first

1. Confirm Issue, acceptance criteria, owned files, branch/`origin/main`, `git status` and relevant review feedback.
2. **Search before reading:** use `rg --files`, focused `rg -n` and changed-path summaries. If source/tests are known, go directly to them; otherwise consult the [task-to-source/test map](task-map.md).
3. Inspect the original source, matching tests and only the necessary specification sections. Search snippets and routing tables are not evidence of semantics.

## Exclude by default

Unrelated Issues/docs/history, stale logs, `dist/`, `build/`, `rust/target/`, `.venv/` and generated indexes. **Exception:** include any of these if directly relevant (e.g. artifact verification).

## Stop or expand

Stop searching when required behavior, source, tests, invariants and checks are clear. Expand to direct consumers, fixtures and contracts on test failures, shared API/JSON changes or missing evidence. Run targeted local checks first **and all applicable required CI/E2E**. Report what was read, run and left unverified; never claim token savings without measured data.

## Read when needed

- Applicable [R01–R20](../../コーディング規約.md) and [workflow](../../doc/ワークフロー/ワークフロー.md) (all mandatory rules still apply)
- Parallel work or optional Context Pack: [collaboration](collaboration.md)
- CI/build/release: [quality gates](quality-gates.md), [internal build reference](development.md)
- Cell detail regressions: [refinement spec](../Refinement_regressions.md)

ObaPick tools are **optional**; adopt one only if repeated work demonstrates value above its maintenance cost. `CLAUDE.md` and Codex use the same `AGENTS.md`.
