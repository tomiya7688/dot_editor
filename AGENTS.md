# Shared agent entrypoint

Claude Code and Codex use **one** policy. Keep this file short; put details in task-specific documents.

1. One Issue per independent branch/PR. Never push directly to `main`, overwrite another agent's worktree, or force-push another agent's branch.
2. Before editing, inspect the Issue/reviews, `git status`, `origin/main` and likely conflicting PRs. Coordinate overlapping files through GitHub.
3. Rust Core is the product authority. Preserve Python 3.10–3.14 build/test support, JSON compatibility and retained detail.
4. Follow [R01–R20](コーディング規約.md), including Japanese declaration comments; never weaken CI, hide failure, or claim missing GUI E2E passed.
5. Open a focused PR with exact validation, risks, file ownership and handoff. A policy/CI change needs its own explicit review.
6. Read the [context router](docs/agents/README.md) and **only relevant linked details**; do not load every document by default.
7. Never mix internal agent workflows, review rules or handoffs into user-facing README/help/API documentation; keep them in `docs/agents/`.
