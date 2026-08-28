"""Integration test: the deterministic ecological core never imports an
optional agent/API dependency (EarlyDesign.md: "ecological core logic must
be deterministic and independent of PydanticAI/FastAPI/provider SDKs").

Parses each deterministic module's AST rather than importing
``pydantic_ai``/``fastapi`` at test-collection time, so this test is
meaningful whether or not the optional extras are installed.
"""

from __future__ import annotations

import ast
from importlib import resources
from pathlib import Path

FORBIDDEN_TOP_LEVEL_MODULES = {"pydantic_ai", "fastapi"}

DETERMINISTIC_PACKAGES = [
    "taxonomy",
    "occurrence",
    "priors",
    "suitability",
    "fusion",
    "risk",
    "evidence",
]


def _python_files_in_package(subpackage: str) -> list[Path]:
    package_root = Path(str(resources.files("s3_ecological"))) / subpackage
    return sorted(package_root.glob("*.py"))


def _imported_top_level_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_deterministic_modules_never_import_pydantic_ai_or_fastapi():
    violations = []
    for subpackage in DETERMINISTIC_PACKAGES:
        for path in _python_files_in_package(subpackage):
            imported = _imported_top_level_modules(path.read_text(encoding="utf-8"))
            forbidden = imported & FORBIDDEN_TOP_LEVEL_MODULES
            if forbidden:
                violations.append(f"{path}: {sorted(forbidden)}")
    assert violations == [], "\n".join(violations)


def test_deterministic_packages_all_exist_and_are_non_empty():
    for subpackage in DETERMINISTIC_PACKAGES:
        files = _python_files_in_package(subpackage)
        assert files, f"expected at least one .py file under {subpackage}/"
