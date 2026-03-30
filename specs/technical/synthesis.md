# Synthesis

## Internal Stages

1. normalize findings
2. deterministically cluster candidates
3. use an LLM only for borderline merge decisions and issue writing
4. apply anchored ICE scoring
5. deduplicate against issues, PRs, and memory
6. emit issue actions

## Minimum Deterministic Baseline

Before any model-backed synthesis is enabled, the repository must support:

- clustering by typed novelty and dedup keys
- deterministic ICE heuristics
- explicit suppression reasons for non-issue-worthy clusters
- dry-run issue rendering with hidden metadata

Deterministic research findings should be conservative:

- competitor fetches alone are not sufficient for high-confidence issue generation
- strategic overlap with `PRODUCT.md` should raise opportunity findings, not hard bugs
- arXiv findings should default to low-confidence strategic opportunities unless reinforced elsewhere

## Scoring Policy

- `impact`, `confidence`, and `ease` are scored on anchored 1-5 scales
- base `ice_score = impact * confidence * ease`
- convergence and strategy alignment can elevate priority
- low-confidence single-source findings should not become autonomous issues

## Memory Use

`pm-agent-memory.json` is advisory:

- calibrate confidence
- detect repeated false positives
- preserve maintainer label preferences

It must not become an opaque hidden prompt dump.
