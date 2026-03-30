"""Replay and validate typed harness scenarios."""

from __future__ import annotations

from pm_agent.harness.models import HarnessScenario, ScenarioResult
from pm_agent.models.contracts import (
    AgentEnvelope,
    AgentName,
    CodebaseAgentOutput,
    DogfoodingAgentOutput,
    ExistingIssuesAgentOutput,
    ResearchAgentOutput,
)

OUTPUT_MODELS: dict[AgentName, type[AgentEnvelope]] = {
    AgentName.RESEARCH: ResearchAgentOutput,
    AgentName.CODEBASE: CodebaseAgentOutput,
    AgentName.DOGFOODING: DogfoodingAgentOutput,
    AgentName.EXISTING_ISSUES: ExistingIssuesAgentOutput,
}


class HarnessRunner:
    def parse_fixture_output(self, scenario: HarnessScenario) -> AgentEnvelope:
        model = OUTPUT_MODELS[scenario.agent]
        return model.model_validate(scenario.fixture_output)

    def evaluate(self, scenario: HarnessScenario) -> ScenarioResult:
        output = self.parse_fixture_output(scenario)
        messages: list[str] = []

        if output.status != scenario.expected.status:
            messages.append(
                f"expected status {scenario.expected.status.value}, got {output.status.value}"
            )

        if len(output.findings) < scenario.expected.min_findings:
            messages.append(
                f"expected at least {scenario.expected.min_findings} findings, got {len(output.findings)}"
            )

        finding_kinds = {finding.kind for finding in output.findings}
        for expected_kind in scenario.expected.required_kinds:
            if expected_kind not in finding_kinds:
                messages.append(f"missing required finding kind {expected_kind.value}")

        finding_tags = {tag for finding in output.findings for tag in finding.tags}
        for expected_tag in scenario.expected.required_tags:
            if expected_tag not in finding_tags:
                messages.append(f"missing required tag {expected_tag}")

        return ScenarioResult(
            scenario_id=scenario.id,
            passed=not messages,
            messages=messages or ["ok"],
        )

    def run_many(self, scenarios: list[HarnessScenario]) -> list[ScenarioResult]:
        return [self.evaluate(scenario) for scenario in scenarios]
