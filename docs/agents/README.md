# Context router for Claude Code and Codex

Use progressive disclosure: `AGENTS.md` is the compact entrypoint, and this table routes to detailed documents only when applicable. Do not duplicate their content into the entrypoint.

| Work | Read |
| --- | --- |
| Any code or docs | [R01–R20](../../コーディング規約.md), [workflow](../../doc/ワークフロー/ワークフロー.md) |
| Agent handoffs, branches, PRs | [collaboration](collaboration.md) |
| Tests, CI, releases | [quality gates](quality-gates.md) |
| Rust retained detail, JSON, resolution | [resolution specification](../Non_destructive_resolution.md) |
| GUI, Python API or CLI | [Command API](../Command_API.md), [CLI detail operations](../CUI_detail_operations.md) |
| Refined cell behavior | [regressions](../Refinement_regressions.md) |

One authoritative document per topic: R01–R20 in `コーディング規約.md`; workflow in `doc/ワークフロー/ワークフロー.md`; behavior in domain specs.

The root `AGENTS.md` is limited to **2,400 UTF-8 bytes and 55 lines** by CI. `CLAUDE.md` imports it with `@AGENTS.md` to support Claude Code configurations that do not automatically load AGENTS.md. Codex reads AGENTS.md directly. Do not include automatic imports for every reference document.
