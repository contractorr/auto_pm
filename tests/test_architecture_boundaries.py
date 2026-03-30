"""Architecture guardrails for the initial scaffold."""

from pathlib import Path

FORBIDDEN_DOMAIN_IMPORT_PREFIXES = ("pm_agent.cli",)
DOMAIN_ROOTS = ("adapters", "agents", "config", "harness", "memory", "models", "orchestration", "repo", "specs", "synthesis")
DOCUMENTED_ROOTS = (
    Path("src/pm_agent"),
    Path("src/pm_agent/adapters"),
    Path("src/pm_agent/repo"),
    Path("src/pm_agent/memory"),
    Path("src/pm_agent/orchestration"),
    Path("src/pm_agent/synthesis"),
    Path("specs"),
    Path("tests"),
)


def _imports_for(path: Path) -> list[str]:
    imports: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("from "):
            imports.append(stripped.split()[1])
        elif stripped.startswith("import "):
            modules = stripped[len("import ") :].split(",")
            imports.extend(part.strip().split()[0] for part in modules)
    return imports


def _python_files_under(root: Path) -> list[Path]:
    return [path for path in root.rglob("*.py") if path.name != "__init__.py"]


def test_domain_modules_do_not_import_cli_surface_directly():
    src_root = Path("src/pm_agent")
    offenders: list[str] = []
    for domain in DOMAIN_ROOTS:
        for path in _python_files_under(src_root / domain):
            for imported in _imports_for(path):
                if imported.startswith(FORBIDDEN_DOMAIN_IMPORT_PREFIXES):
                    offenders.append(f"{path}: {imported}")
    assert offenders == []


def test_key_roots_have_local_readmes():
    missing = [str(root / "README.md") for root in DOCUMENTED_ROOTS if not (root / "README.md").exists()]
    assert missing == []
