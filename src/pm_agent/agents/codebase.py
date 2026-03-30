"""Local codebase agent using conservative repository heuristics."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pm_agent.agents.base import AgentExecutionContext, BaseAgent
from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    CodebaseAgentOutput,
    ComponentSummary,
    Evidence,
    Finding,
    FindingKind,
    Severity,
    SourceRef,
    SourceType,
)

CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".yml", ".yaml"}
TEST_MARKERS = ("test", "spec")


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    except OSError:
        return 0


def _iter_files(root: Path, ignore_paths: list[Path]) -> list[Path]:
    ignore_parts = {path.parts[0] for path in ignore_paths if path.parts}
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignore_parts for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() in CODE_SUFFIXES:
            files.append(path)
    return files


def _component_candidates(repo_root: Path, project_roots: list[Path]) -> list[ComponentSummary]:
    base_root = repo_root.resolve()
    components: list[ComponentSummary] = []
    for project_root in project_roots:
        root = (base_root / project_root).resolve()
        if not root.exists() or not root.is_dir():
            continue
        for child in sorted(root.iterdir(), key=lambda path: path.name.lower()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            files = [
                path
                for path in child.rglob("*")
                if path.is_file() and path.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx"}
            ]
            if not files:
                continue
            components.append(
                ComponentSummary(
                    name=child.name,
                    paths=[str(child.relative_to(base_root)).replace("\\", "/")],
                    responsibilities=[f"Contains {len(files)} source files."],
                    risks=[],
                )
            )
    return components[:10]


def _build_findings(context: AgentExecutionContext, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    repo_root = context.repo_root
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

    has_tests = any(any(marker in path.name.lower() for marker in TEST_MARKERS) for path in files)
    if not has_tests:
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
                        summary="Repository scan found no test or spec files.",
                        source_refs=[
                            SourceRef(
                                source_type=SourceType.REPO_FILE,
                                source_id="repo-scan",
                                locator=str(repo_root),
                            )
                        ],
                    )
                ],
                proposed_direction="Add at least a smoke test layer before enabling autonomous lifecycle actions.",
            )
        )

    return findings


class CodebaseAgent(BaseAgent):
    name = AgentName.CODEBASE

    def run(self, context: AgentExecutionContext) -> CodebaseAgentOutput:
        started_at = datetime.now(UTC)
        files = _iter_files(context.repo_root, context.config.repo.ignore_paths)
        components = _component_candidates(context.repo_root, context.config.repo.project_roots)
        hotspot_files = [
            str(path.relative_to(context.repo_root)).replace("\\", "/")
            for path in sorted(files, key=_line_count, reverse=True)[:5]
            if _line_count(path) >= 200
        ]
        test_files = sum(1 for path in files if any(marker in path.name.lower() for marker in TEST_MARKERS))
        doc_files = sum(1 for path in files if path.suffix.lower() == ".md")
        findings = _build_findings(context, files)
        repo_summary = (
            f"Scanned {len(files)} tracked source/docs files across "
            f"{len(components)} component directories, {doc_files} markdown docs, "
            f"and {test_files} detected test files."
        )
        return CodebaseAgentOutput(
            agent=AgentName.CODEBASE,
            status=AgentStatus.SUCCESS,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            findings=findings,
            repo_summary=repo_summary,
            components=components,
            changed_files=[],
            hotspot_files=hotspot_files,
        )
