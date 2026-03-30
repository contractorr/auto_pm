# auto_pm

Spec-driven autonomous PM and UX agent scaffolding for full-stack applications.

This repository starts with contracts and harnesses first:

- `specs/` is the source of truth for architecture, synthesis, and maintenance policy.
- `src/pm_agent/models/` defines typed contracts shared across agents.
- `src/pm_agent/harness/` provides replayable fixture scenarios so agent behavior can be regression-tested without human supervision.
- `tests/` enforces architecture boundaries, spec presence, and contract stability.

## Current scope

This first pass establishes the build-ready skeleton:

- validated `pm-config.yml` schema
- typed agent and synthesis contracts
- a spec manifest and checker
- a replay harness for agent outputs
- local capability discovery and `PRODUCT.md` loading
- manifest-based codebase retrieval and deterministic component summaries
- optional Anthropic-backed codebase review with deterministic fallback
- deterministic dry-run synthesis from fixture inputs
- live local collection from a checked-out repo plus GitHub issue ingestion
- reusable GitHub Actions workflow support for scheduled or push-driven execution in target repos
- optional Anthropic-backed research review for competitor pages and arXiv papers with deterministic fallback
- optional Anthropic-backed synthesis review and issue writing with deterministic fallback
- portfolio-level synthesis budgeting so matched updates are preserved while only new issue creation consumes the per-run budget
- architecture tests that keep the repo spec-driven over time

Live integrations with GitHub, Anthropic, Playwright, Docker, and arXiv come next.

Each live run also persists a structured JSON report under `.pm-agent-artifacts/<run_id>/run-report.json` and refreshes `.pm-agent-run.json` at the repo root for quick inspection and workflow artifact upload.

## Commands

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .[dev]

pm-agent specs check
pm-agent config validate pm-config.example.yml
pm-agent harness validate
pm-agent discover inspect --config pm-config.example.yml --repo-root tests/fixtures/repos/sample-app
pm-agent run dry --config pm-config.example.yml --repo-root tests/fixtures/repos/sample-app --fixture tests/fixtures/pipeline/sample-dry-run.yaml
pm-agent run live --config pm-config.example.yml --repo-root ../stewardme
pm-agent run live --config pm-config.example.yml --repo-root ../stewardme --write-mode comment_only
pytest
```

For live dogfooding, install the browser once:

```bash
python -m playwright install chromium
```

To dogfood a deployed site instead of starting a local instance, set `runtime.mode: external_url`, point `runtime.service_urls` at the live base URL, and use `dogfooding.auth_strategy: credentials` with env-backed secrets. Remote login forms can then use standard `fill` steps with `{{ credentials.username }}`, `{{ credentials.password }}`, and `{{ credentials.totp_code }}` placeholders.
For apps that already have reusable browser auth bootstrap, `dogfooding.auth_strategy` also supports `storage_state` and `setup_script`. Sensitive steps can opt into `artifact_mode: redact` or `artifact_mode: skip`, and `redact_selectors` can clear additional fields before any screenshot or accessibility snapshot is captured.

For GitHub writeback, export `GITHUB_TOKEN` first. Safe rollout order:

1. `write_mode: disabled`
2. `--write-mode comment_only`
3. `--write-mode apply`

For model-backed synthesis, enable the `anthropic` block in `pm-config.yml` and export the configured API key env var. If the key is missing, synthesis falls back to deterministic behavior and emits a warning in the CLI JSON output.

## Automation

This repo now ships with:

- [`.github/workflows/ci.yml`](./.github/workflows/ci.yml) for lint, tests, spec checks, harness validation, and a dry-run smoke test
- [`.github/workflows/reusable-pm-agent.yml`](./.github/workflows/reusable-pm-agent.yml) for scheduled or push-triggered execution from a target repository

The reusable workflow is meant to be called from the application repository that owns the real `pm-config.yml` and `PRODUCT.md`. A caller workflow can look like:

```yaml
name: pm-agent

on:
  push:
    branches:
      - main
  schedule:
    - cron: "0 9 * * 1-5"
  workflow_dispatch:

jobs:
  pm-agent:
    uses: contractorr/auto_pm/.github/workflows/reusable-pm-agent.yml@main
    with:
      config_path: pm-config.yml
      repo_root: .
      trigger: schedule
      write_mode: comment_only
      install_playwright: true
    secrets: inherit
```

If the target repo wants long-lived calibration, keep `persist_memory_commit: true` so `.github/pm-agent-memory.json` is committed back automatically when it changes.
Workflow uploads now include the machine-readable run report plus the `.pm-agent-artifacts/` directory, which captures dogfooding screenshots and accessibility snapshots when present.

## Local-only Files

This code repo keeps only examples under `PRODUCT.example.md` and `pm-config.example.yml`. The real `PRODUCT.md` and `pm-config.yml` are intentionally ignored locally and should live only in the target application repositories that the agent operates on.

## Layout

```text
specs/                  design source of truth
src/pm_agent/           runtime package
tests/                  contract and harness regression tests
pm-config.example.yml   example repo configuration
PRODUCT.example.md      example product strategy document
AGENTS.md               operating instructions for future coding agents
```
