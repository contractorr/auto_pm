# Synthesis

## Internal Stages

1. normalize findings
2. deterministically cluster candidates
3. optionally use an LLM for conservative cluster review and issue writing
4. apply anchored ICE scoring
5. deduplicate against issues, PRs, and memory
6. run a portfolio-level selection pass so only `create` actions consume the per-run issue budget
7. emit issue actions

## Minimum Deterministic Baseline

Before any model-backed synthesis is enabled, the repository must support:

- clustering by typed novelty and dedup keys
- deterministic ICE heuristics
- explicit suppression reasons for non-issue-worthy clusters
- dry-run issue rendering with hidden metadata

## Optional Model-Backed Review

When Anthropic-backed synthesis is enabled:

- deterministic scoring and deduplication remain authoritative
- model review may refine wording or suppress weak unmatched proposals
- model-backed portfolio review may reorder or suppress unmatched `create` proposals, but must not drop matched update/comment targets
- model review must not rewrite deterministic matched issue targets
- model issue writing must fall back to deterministic markdown on API or parsing failures
- runs should emit synthesis warnings when model-backed synthesis is requested but unavailable

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
