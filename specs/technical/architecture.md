# Architecture

## Principles

1. Specs first, code second.
2. Deterministic normalization before any LLM synthesis.
3. Adapters isolate third-party systems.
4. Agents produce typed envelopes even when degraded.
5. Autonomous issue lifecycle actions only affect AI-authored issues with metadata.

## Package Boundaries

- `config/` owns `pm-config.yml` parsing and validation.
- `models/` owns stable cross-agent contracts.
- `repo/` owns product-context loading, local capability discovery, manifest building, and retrieval primitives.
- `agents/` owns data collection and summarization boundaries.
- `synthesis/` owns normalization, clustering, scoring, deduplication, and issue writing.
- optional Anthropic-backed synthesis refinement must live behind the deterministic synthesis boundary.
- `orchestration/` owns dry-run execution and future live run coordination.
- `memory/` owns persistent calibration data loading and summarization.
- `harness/` owns replayable scenarios and expectation checks.
- future `adapters/` will own GitHub, Anthropic, Playwright, Docker, and arXiv clients.

## Trigger Strategy

- `push` runs should be diff-aware and budget-constrained.
- scheduled runs should perform deeper research, broader dogfooding, and lifecycle reconciliation.
- reusable GitHub Actions workflows should be the primary automation entrypoint for target repositories.
- target repositories should own the real `pm-config.yml`, `PRODUCT.md`, and persisted `.github/pm-agent-memory.json`.
- `push` runs should skip heavyweight research, reuse changed-file context across agents, and limit issue creation budgets more aggressively than scheduled runs.
- overlapping live runs against the same target repo should be serialized through both workflow concurrency and a local repository lock.
- live runs should persist a structured run report and indexed artifacts under `.pm-agent-artifacts/<run_id>/` for later audit and debugging.

## Local-First Runtime

Before live adapters are introduced, the project must support:

1. local capability discovery from a checked-out repo
2. product-context loading from `PRODUCT.md`
3. deterministic dry-run synthesis from typed fixture inputs
4. replayable regression tests for the full dry-run path

## Live Collection Slice

The first live execution slice should support:

1. a local codebase agent that summarizes the checked-out repo and emits only conservative heuristic findings
2. a GitHub-backed existing-issues agent for open issues, open PRs, and recent closed issues
3. a live collection runner that feeds these real agent outputs into deterministic synthesis
4. adapter injection so tests do not depend on live network calls

## Codebase Understanding Contract

- the codebase agent should rely on a deterministic repo manifest instead of ad hoc directory walking
- repo summaries should include component-level structure, hotspot files, and changed-file context when git metadata is available
- optional model-backed codebase review may refine summaries, components, and findings, but manifest and retrieval logic should remain reusable without a model
- missing API keys or model failures must fall back to deterministic repo understanding with explicit warnings
- dogfooding on `push` should scope journeys using changed-file hints and fall back to a minimal safe subset when no match is found

## Deterministic Research Slice

The first research implementation should:

1. fetch competitor pages deterministically without LLM summarization
2. read arXiv category feeds through the public Atom API
3. emit research findings only when there is explicit overlap with product priorities
4. degrade to typed warnings when network access fails

Optional model-backed research review may sit on top of the deterministic fetch layer:

- deterministic source fetching remains authoritative
- model review may refine snapshots and decide whether a source is issue-worthy
- missing API keys or model failures must fall back to deterministic research findings with explicit warnings

## Maintenance Contract

Every material behavior change must ship with:

1. a spec update
2. a contract or harness test update
3. a typed model change if the data shape changed
