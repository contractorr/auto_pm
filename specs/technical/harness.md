# Harness

## Goal

Agents must be maintainable through replayable machine-checkable scenarios.

## Requirements

1. Harness scenarios live under `tests/fixtures/harness/`.
2. Each scenario is typed and validated before execution.
3. The harness must support fixture replay without live network calls.
4. Expectations are explicit: status, finding count, required kinds, and required tags.
5. Future live harness runs should reuse the same scenario model.
6. The repo must also support full dry-run pipeline fixtures for discovery plus synthesis regression tests.

## Regression Policy

- new agent behavior should add a scenario
- contract-breaking changes must update existing scenarios
- CI should fail if scenario fixtures no longer parse under current models
