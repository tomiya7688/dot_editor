# Claude Code × Codex: cooperation and ownership

## Purpose

Prevent two agents from overwriting or unknowingly reviewing their own changes. An agent's report is not an approval; human review plus CI decide acceptance.

## One work unit

1. Check Issue priority/dependencies, related open/rejected PRs and review comments. Fetch `origin/main` and inspect `git status`; never discard unrelated work.
2. Use separate worktrees/clones and uniquely named `issue-N-claude-...` or `issue-N-codex-...` branches. Declare Issue, affected files and owner in the Issue or PR before editing shared areas.
3. Do not edit the same files concurrently. One agent owns the patch; the other reviews or works on a separate Issue. Agree on public interfaces/fixtures before parallel implementation.
4. Keep commits scoped to the Issue. Do not silently rebase or force-push another agent's branch, directly push to `main`, remove tests, or relax CI to make a build green.
5. Preserve Rust Core authority, Python 3.10–3.14 buildability, versioned JSON and retained detail. Interface/serialization changes need golden fixtures and language-compatibility tests.

## Transfer and completion

For each handoff, record **Issue, agent, branch and SHA, owned files, finished work, exact test commands/results, risks/blockers, unresolved comments, next action** in the PR/Issue. The receiving agent must fetch and inspect the diff; previous checks do not prove the changed HEAD passes.

Use the shared PR template. A skipped or unavailable GUI E2E must be marked **unverified**, never successful. Only merge after all required status checks pass and an independent reviewer checks intent, data safety, performance and human-language documentation. Failure, cancellation or pending status is not approval. Human authorization is required for destructive changes or CI policy relaxation.
