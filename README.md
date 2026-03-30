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
- deterministic dry-run synthesis from fixture inputs
- live local collection from a checked-out repo plus GitHub issue ingestion
- reusable GitHub Actions workflow support for scheduled or push-driven execution in target repos
- architecture tests that keep the repo spec-driven over time

Live integrations with GitHub, Anthropic, Playwright, Docker, and arXiv come next.

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

For GitHub writeback, export `GITHUB_TOKEN` first. Safe rollout order:

1. `write_mode: disabled`
2. `--write-mode comment_only`
3. `--write-mode apply`

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
