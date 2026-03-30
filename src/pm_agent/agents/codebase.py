"""Local codebase agent using manifest-based repository retrieval."""

from __future__ import annotations

from datetime import UTC, datetime

from pm_agent.agents.base import AgentExecutionContext, BaseAgent
from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    CodebaseAgentOutput,
    Evidence,
    Finding,
    FindingKind,
    Severity,
    SourceRef,
    SourceType,
)
from pm_agent.repo.manifest import RepoManifest, build_repo_manifest
from pm_agent.repo.retrieval import hotspot_files
from pm_agent.repo.summarizer import summarize_components, summarize_repo


def _build_findings(context: AgentExecutionContext, manifest: RepoManifest) -> list[Finding]:
    findings: list[Finding] = []
    caps = context.capabilities
    timestamp = context.run.run_id

    if caps is not None and not caps.product_file_exists:
        findings.append(
            Finding(
                finding_id=f"{timestamp}-missing-product",
                agent=AgentName.CODEBASE,
                kind=FindingKind.PRODUCT_GAP,
                title="Repo is missing PRODUCT.md strategy context",
                problem_statement="The repository does not include the configured PRODUCT.md file.",
                user_impact="The PM agent cannot align prioritization to product strategy.",
                severity=Severity.MEDIUM,
                raw_confidence=0.95,
                novelty_key="missing-product-context",
                dedup_keys=["missing-product-context"],
                tags=["strategy", "config"],
                evidence=[
                    Evidence(
                        summary="Configured product context file was not found in the repo.",
                        source_refs=[
                            SourceRef(
                                source_type=SourceType.REPO_DOC,
                                source_id="product-file",
                                repo_path=str(context.config.repo.product_file).replace("\\", "/"),
                            )
                        ],
                    )
                ],
                proposed_direction="Add and maintain PRODUCT.md so synthesis can reason against strategy.",
            )
        )

    if context.config.runtime.mode.value == "docker_compose" and caps is not None and not caps.docker_compose_ready:
        findings.append(
            Finding(
                finding_id=f"{timestamp}-missing-compose",
                agent=AgentName.CODEBASE,
                kind=FindingKind.RELIABILITY,
                title="Configured Docker Compose runtime is missing",
                problem_statement="The PM agent is configured to use Docker Compose, but the compose file is absent.",
                user_impact="Dogfooding and repeatable local validation will fail.",
                severity=Severity.HIGH,
                raw_confidence=0.96,
                novelty_key="missing-docker-compose",
                dedup_keys=["missing-docker-compose"],
                tags=["runtime", "dogfooding"],
                evidence=[
                    Evidence(
                        summary="Configured compose file was not found in the repo.",
                        source_refs=[
                            SourceRef(
                                source_type=SourceType.REPO_FILE,
                                source_id="compose-file",
                                repo_path=str(context.config.runtime.compose_file).replace("\\", "/")
                                if context.config.runtime.compose_file
                                else None,
                            )
                        ],
                    )
                ],
                proposed_direction="Either add the compose file or switch runtime mode in pm-config.yml.",
            )
        )

    if not manifest.test_files:
        findings.append(
            Finding(
                finding_id=f"{timestamp}-missing-tests",
                agent=AgentName.CODEBASE,
                kind=FindingKind.TECHNICAL_RISK,
                title="Repo has no detectable test coverage",
                problem_statement="No files matching common test naming conventions were found.",
                user_impact="The PM agent cannot reliably distinguish regressions from intended changes.",
                severity=Severity.MEDIUM,
                raw_confidence=0.75,
                novelty_key="missing-tests",
                dedup_keys=["missing-tests"],
                tags=["testing"],
                evidence=[
                    Evidence(
                        summary="Repository manifest found no test, spec, or e2e files.",
                        source_refs=[
                            SourceRef(
                                source_type=SourceType.REPO_FILE,
                                source_id="repo-manifest",
                                locator=context.repo_root.as_posix(),
                            )
                        ],
                    )
                ],
                proposed_direction="Add at least a smoke test layer before enabling autonomous lifecycle actions.",
            )
        )

    if manifest.source_files and not manifest.doc_files:
        findings.append(
            Finding(
                finding_id=f"{timestamp}-missing-docs",
                agent=AgentName.CODEBASE,
                kind=FindingKind.PRODUCT_GAP,
                title="Repo has little or no supporting documentation",
                problem_statement="The repository has source files but no markdown documentation beyond config-level metadata.",
                user_impact="Agents and maintainers have less context for prioritization, onboarding, and issue triage.",
                severity=Severity.LOW,
                raw_confidence=0.7,
                novelty_key="missing-repo-docs",
                dedup_keys=["missing-repo-docs"],
                tags=["docs"],
                evidence=[
                    Evidence(
                        summary="Repository manifest found source files but no markdown docs.",
                        source_refs=[
                            SourceRef(
                                source_type=SourceType.REPO_DOC,
                                source_id="repo-manifest",
                                locator=context.repo_root.as_posix(),
                            )
                        ],
                    )
                ],
                proposed_direction="Add lightweight technical docs or feature notes for primary components.",
            )
        )

    return findings


class CodebaseAgent(BaseAgent):
    name = AgentName.CODEBASE

    def run(self, context: AgentExecutionContext) -> CodebaseAgentOutput:
        started_at = datetime.now(UTC)
        manifest = build_repo_manifest(
            context.repo_root,
            project_roots=context.config.repo.project_roots,
            ignore_paths=context.config.repo.ignore_paths,
        )
        components = summarize_components(manifest)
        findings = _build_findings(context, manifest)
        repo_summary = summarize_repo(manifest, components=components)
        return CodebaseAgentOutput(
            agent=AgentName.CODEBASE,
            status=AgentStatus.SUCCESS,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            findings=findings,
            repo_summary=repo_summary,
            components=components,
            changed_files=context.changed_files,
            hotspot_files=hotspot_files(manifest),
        )
