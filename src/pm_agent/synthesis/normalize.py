"""Normalize synthesis inputs into a unified finding stream."""

from __future__ import annotations

from pm_agent.models.contracts import AgentEnvelope, Finding, SynthesisInput


def agent_outputs_from_input(synthesis_input: SynthesisInput) -> list[AgentEnvelope]:
    outputs: list[AgentEnvelope] = []
    for output in (
        synthesis_input.research,
        synthesis_input.codebase,
        synthesis_input.dogfooding,
        synthesis_input.existing_issues,
    ):
        if output is not None:
            outputs.append(output)
    return outputs


def collect_findings(synthesis_input: SynthesisInput) -> list[Finding]:
    findings: list[Finding] = []
    for output in agent_outputs_from_input(synthesis_input):
        findings.extend(output.findings)
    return findings
