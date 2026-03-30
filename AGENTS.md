# Agent Working Agreement

This repository is maintained in a spec-driven way.

Rules for future agents:

1. Update `specs/` before or alongside behavior changes.
2. Preserve typed contracts in `src/pm_agent/models/`; breaking changes require test updates and spec updates in the same change.
3. Add or update harness scenarios in `tests/fixtures/harness/` for any new agent behavior.
4. Keep synthesis deterministic where possible; use LLMs only after deterministic normalization and filtering.
5. Do not add direct third-party integration code without a matching adapter boundary.
6. Auto-maintenance features must be regression-tested with replay fixtures before being enabled against live repos.
