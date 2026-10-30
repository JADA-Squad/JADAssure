"""GR-02 structural guard: engine domains must never import the ai domain (INFRA-002, decision 0001 D-2)."""

import ast
import pathlib

DOMAINS_DIR = pathlib.Path(__file__).resolve().parents[1] / "app" / "domains"
AI_FREE_DOMAINS = ["matching", "rules", "cases", "recovery", "reporting"]
FORBIDDEN = "app.domains.ai"


def ai_imports(source: str, module_package: str, forbidden: str = FORBIDDEN) -> list[str]:
    """Return every import in `source` that resolves to the `forbidden` package (default: the ai domain)."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import: resolve against the module's package
                base = module_package.split(".")[: len(module_package.split(".")) - node.level + 1]
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            names = [mod] + [f"{mod}.{alias.name}" for alias in node.names]
        else:
            continue
        found += [n for n in names if n == forbidden or n.startswith(forbidden + ".")]
    return found


def test_checker_detects_absolute_and_relative_imports():
    assert ai_imports("import app.domains.ai.provider", "app.domains.rules")
    assert ai_imports("from app.domains.ai import provider", "app.domains.rules")
    assert ai_imports("from app.domains import ai", "app.domains.rules")
    assert ai_imports("from ..ai import stub", "app.domains.rules")
    assert not ai_imports("from app.domains.matching import terms", "app.domains.rules")
    assert not ai_imports("import app.domains.aircraft", "app.domains.rules")


def test_engine_domains_do_not_import_ai():
    violations = []
    for domain in AI_FREE_DOMAINS:
        for path in (DOMAINS_DIR / domain).rglob("*.py"):
            package = "app.domains." + ".".join(path.relative_to(DOMAINS_DIR).with_suffix("").parts[:-1])
            for name in ai_imports(path.read_text(encoding="utf-8"), package):
                violations.append(f"{path.relative_to(DOMAINS_DIR)} imports {name}")
    assert violations == []


def test_engine_domains_do_not_import_the_assistant():
    """Decision 0009 D-7: the assistant may call the engine; the engine never depends on the assistant."""
    violations = []
    for domain in AI_FREE_DOMAINS:
        for path in (DOMAINS_DIR / domain).rglob("*.py"):
            package = "app.domains." + ".".join(path.relative_to(DOMAINS_DIR).with_suffix("").parts[:-1])
            for name in ai_imports(path.read_text(encoding="utf-8"), package, "app.domains.assistant"):
                violations.append(f"{path.relative_to(DOMAINS_DIR)} imports {name}")
    assert violations == []
