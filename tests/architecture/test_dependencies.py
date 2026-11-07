"""Architecture tests for the layer dependency rule (ARCHITECTURE.md section 2)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Final

import pytest

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

LAYER_PREFIXES: Final = (
    ("api/domain/", "domain"),
    ("api/ports/", "ports"),
    ("api/application/", "application"),
    ("api/adapters/", "adapters"),
    ("ml/", "ml"),
)
ALLOWED_PACKAGES: Final = {
    "domain": ("api.domain",),
    "ports": ("api.domain", "api.ports"),
    "application": ("api.domain", "api.ports", "api.application"),
}
ML_FORBIDDEN_PACKAGES: Final = ("api.ports", "api.application", "api.adapters")


def module_layer(relative_path: Path) -> str | None:
    """Return the layer a repository-relative path belongs to, or None."""
    posix = relative_path.as_posix()
    if posix == "api/main.py":
        return "main"
    for prefix, layer in LAYER_PREFIXES:
        if posix.startswith(prefix):
            return layer
    return None


def imported_modules(path: Path) -> tuple[str, ...]:
    """Return every module named by an import statement in the file, at any depth."""
    modules: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append("." * node.level + (node.module or ""))
            if node.level == 0 and node.module == "api":
                modules.extend(f"api.{alias.name}" for alias in node.names)
    return tuple(modules)


def within(module: str, package: str) -> bool:
    """Return True when the module is the package or lives under it."""
    return module == package or module.startswith(package + ".")


def is_allowed(layer: str, module: str) -> bool:
    """Return True when a module of the given layer may import the module."""
    if module.startswith(".") or within(module, "api.main"):
        return False
    packages = ALLOWED_PACKAGES.get(layer)
    if packages is not None:
        is_stdlib = module.split(".")[0] in sys.stdlib_module_names
        return is_stdlib or any(within(module, package) for package in packages)
    if layer == "ml":
        return not any(within(module, package) for package in ML_FORBIDDEN_PACKAGES)
    return True


def dependency_violations(root: Path) -> tuple[str, ...]:
    """Return one line per import that breaks the layer rule under root/api and root/ml."""
    violations: list[str] = []
    paths = sorted(path for name in ("api", "ml") for path in (root / name).rglob("*.py"))
    for path in paths:
        relative = path.relative_to(root)
        layer = module_layer(relative)
        if layer is None:
            continue
        violations.extend(
            f"{relative.as_posix()}: {layer} must not import {module}"
            for module in imported_modules(path)
            if not is_allowed(layer, module)
        )
    return tuple(violations)


def plant(root: Path, relative_path: str, body: str) -> None:
    """Write a file with the given body under root, creating parent directories."""
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body + "\n", encoding="utf-8")


def test_dependencies_repository_has_no_violations() -> None:
    assert dependency_violations(REPO_ROOT) == ()


def test_dependencies_no_init_files() -> None:
    names = ("api", "ml", "tests", "scripts")
    found = [
        path.relative_to(REPO_ROOT).as_posix()
        for name in names
        for path in (REPO_ROOT / name).rglob("__init__.py")
    ]
    assert found == []


def test_dependencies_domain_rejects_third_party(tmp_path: Path) -> None:
    plant(tmp_path, "api/domain/bad.py", "import numpy")
    assert dependency_violations(tmp_path) == ("api/domain/bad.py: domain must not import numpy",)


def test_dependencies_domain_allows_stdlib_and_domain(tmp_path: Path) -> None:
    plant(tmp_path, "api/domain/ok.py", "import re\nfrom api.domain.errors import AppError")
    assert dependency_violations(tmp_path) == ()


def test_dependencies_type_checking_import_counted(tmp_path: Path) -> None:
    body = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import numpy"
    plant(tmp_path, "api/domain/tc.py", body)
    assert dependency_violations(tmp_path) == ("api/domain/tc.py: domain must not import numpy",)


def test_dependencies_relative_import_rejected(tmp_path: Path) -> None:
    plant(tmp_path, "api/domain/rel.py", "from . import errors")
    assert dependency_violations(tmp_path) == ("api/domain/rel.py: domain must not import .",)


def test_dependencies_ports_rejects_adapters(tmp_path: Path) -> None:
    plant(tmp_path, "api/ports/bad.py", "from api.adapters.settings import load_settings")
    assert dependency_violations(tmp_path) == (
        "api/ports/bad.py: ports must not import api.adapters.settings",
    )


def test_dependencies_application_rejects_ml(tmp_path: Path) -> None:
    plant(tmp_path, "api/application/bad.py", "import ml.data")
    assert dependency_violations(tmp_path) == (
        "api/application/bad.py: application must not import ml.data",
    )


def test_dependencies_nobody_imports_main(tmp_path: Path) -> None:
    plant(tmp_path, "api/adapters/bad.py", "from api.main import app")
    assert dependency_violations(tmp_path) == (
        "api/adapters/bad.py: adapters must not import api.main",
    )


def test_dependencies_ml_rejects_application(tmp_path: Path) -> None:
    plant(tmp_path, "ml/bad.py", "from api.application.analyze import AnalyzeComment")
    assert dependency_violations(tmp_path) == (
        "ml/bad.py: ml must not import api.application.analyze",
    )


def test_dependencies_ml_allows_domain_and_third_party(tmp_path: Path) -> None:
    plant(tmp_path, "ml/ok.py", "from api.domain.entities import Polarity\nimport sklearn")
    assert dependency_violations(tmp_path) == ()


def test_dependencies_bare_api_import_rejected(tmp_path: Path) -> None:
    plant(tmp_path, "api/domain/pkg.py", "from api import domain")
    assert dependency_violations(tmp_path) == ("api/domain/pkg.py: domain must not import api",)


def test_dependencies_from_api_import_submodule_ml(tmp_path: Path) -> None:
    plant(tmp_path, "ml/bad.py", "from api import adapters")
    assert dependency_violations(tmp_path) == ("ml/bad.py: ml must not import api.adapters",)


def test_dependencies_from_api_import_main(tmp_path: Path) -> None:
    plant(tmp_path, "api/adapters/bad.py", "from api import main")
    assert dependency_violations(tmp_path) == (
        "api/adapters/bad.py: adapters must not import api.main",
    )


def test_dependencies_syntax_error_propagates(tmp_path: Path) -> None:
    plant(tmp_path, "api/domain/broken.py", "def (")
    with pytest.raises(SyntaxError):
        dependency_violations(tmp_path)
