# Claude Code × Codex: cooperation and ownership

## Purpose

Prevent two agents from overwriting each other's work. The implementer reviews their own diff as defined in [the role workflow](../../doc/ワークフロー/ワークフロー.md); an agent's self-review is not a GitHub approval, and required CI plus any review that branch protection actually requires decide acceptance.

## One work unit

1. Check Issue priority/dependencies, related open/rejected PRs and review comments. Fetch `origin/main` and inspect `git status`; never discard unrelated work.
2. Use separate worktrees/clones and uniquely named `issue-N-claude-...` or `issue-N-codex-...` branches. Declare Issue, affected files and owner in the Issue or PR before editing shared areas.
3. Do not edit the same files concurrently. One agent owns the patch; the other reviews or works on a separate Issue. Agree on public interfaces/fixtures before parallel implementation.
4. Keep commits scoped to the Issue. Do not silently rebase or force-push another agent's branch, directly push to `main`, remove tests, or relax CI to make a build green.
5. Preserve Rust Core authority, Python 3.10–3.14 buildability, versioned JSON and retained detail. Interface/serialization changes need golden fixtures and language-compatibility tests.

## Documentation boundary

The product README, user help and public API guides explain how the software is used. **Never insert agent workflow, Issue ownership, CI approval instructions, review checklists or handoffs there.** Keep internal working procedures under `docs/agents/`, linked from the compact `AGENTS.md` entrypoint only.

## Optional Context Pack for multi-step handoffs

For a cross-agent or resumed task spanning several files, leave a **short task-specific Context Pack** in the Issue/PR, not in `AGENTS.md` or a product guide:

- Goal and acceptance criteria (link to the Issue).
- First source/tests, owned files and the reason they were chosen.
- Invariants, excluded scope and relevant contract links.
- Branch/base/HEAD SHA, completed verification, blockers, next action.

Link to source documents rather than copying long requirements or logs. This is a disposable working summary, not a second specification. Skip it for a small task whose target and test are already obvious. Refresh file ownership and HEAD when handing off; never assume an old summary describes the new branch.

## Transfer and completion

For each handoff, record **Issue, agent, branch and SHA, owned files, finished work, exact test commands/results, risks/blockers, unresolved comments, next action** in the PR/Issue. The receiving agent must fetch and inspect the diff; previous checks do not prove the changed HEAD passes.

Use the shared PR template. A skipped or unavailable GUI E2E must be marked **unverified**, never successful. Merge only after all required status checks pass and the implementer's recorded self-review covers intent, data safety, performance and human-language documentation, following [the role workflow](../../doc/ワークフロー/ワークフロー.md). Do not wait for a repository-wide reviewer's approval, and never fake a GitHub approval. Failure, cancellation or pending status is not approval. Human authorization is required for destructive changes or CI policy relaxation.
