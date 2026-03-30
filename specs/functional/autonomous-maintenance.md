# Autonomous Maintenance

The project should remain operable without frequent human babysitting.

## Guardrails

- config validation runs before execution
- missing required specs fail fast
- harness replay runs in CI
- agents can degrade gracefully and still emit structured warnings
- issue lifecycle automation is scoped to AI-authored issues only
- reusable workflow runs upload a machine-readable report artifact
- persisted memory updates can be committed automatically without editing source files by hand

## Rollout Model

1. fixture replay and contract tests
2. dry-run issue generation
3. live collection from local repo plus GitHub issues
4. comment-only mode on GitHub
5. controlled issue creation and AI-authored issue updates
6. controlled lifecycle automation

## Writeback Guardrails

- `comment_only` mode must never create new issues
- body updates should only target AI-authored issues with PM-agent metadata
- non-AI issues and PRs should receive comments rather than rewrites
- every writeback action should emit a structured result for auditability
- automatic memory commits should be limited to `.github/pm-agent-memory.json`

## Workflow Contract

- this repository must ship a CI workflow that runs lint, tests, spec checks, harness validation, and a dry-run smoke test
- this repository must ship a reusable workflow that a target repository can call on `push`, `schedule`, or `workflow_dispatch`
- the reusable workflow must support optional Playwright browser installation and optional memory-file commits
- the real `pm-config.yml` and `PRODUCT.md` belong in the target repository, not in this code repository
