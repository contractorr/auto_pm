# Contracts

## Contract Rules

1. All inter-agent payloads use Pydantic models.
2. Agents return partial structured output instead of raising away all context.
3. The synthesis layer consumes normalized findings, not raw tool transcripts.
4. Hidden issue metadata must include `cluster_id`, source fingerprints, and agent version.

## Stable Artifacts

- `RunContext`
- `ProductContext`
- `Finding`
- `CapabilitySnapshot`
- agent-specific output envelopes
- `SynthesisInput`
- `IssueProposal`
- `PMAgentMemory`
- writeback action/result records

## Backwards Compatibility

Breaking changes to these models require:

1. spec updates
2. fixture updates
3. tests that assert the new shape explicitly
