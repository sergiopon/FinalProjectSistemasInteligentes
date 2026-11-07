"""Architecture tests for module and class size limits (ARCHITECTURE.md section 6)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

MAX_MODULE_LINES: Final = 300
MAX_CLASS_LINES: Final = 150
MODULE_LINE_EXEMPTIONS: Final = frozenset({"api/adapters/http_schemas.py", "ml/schemas.py"})
SCANNED_DIRS: Final = ("api", "ml", "tests", "scripts")


def class_violations(relative_path: str, tree: ast.AST) -> list[str]:
    """Return one line per class in the tree longer than MAX_CLASS_LINES."""
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        count = (node.end_lineno or node.lineno) - node.lineno + 1
        if count > MAX_CLASS_LINES:
            violations.append(
                f"{relative_path}:{node.lineno}: class {node.name} has {count} lines > 150"
            )
    return violations


def size_violations(root: Path) -> tuple[str, ...]:
    """Return one line per module or class over its size limit under the scanned directories."""
    violations: list[str] = []
    paths = sorted(path for name in SCANNED_DIRS for path in (root / name).rglob("*.py"))
    for path in paths:
        relative_path = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        line_count = len(text.splitlines())
        if line_count > MAX_MODULE_LINES and relative_path not in MODULE_LINE_EXEMPTIONS:
            violations.append(f"{relative_path}: {line_count} lines > 300")
        violations.extend(class_violations(relative_path, ast.parse(text)))
    return tuple(violations)


def plant(root: Path, relative_path: str, lines: list[str]) -> None:
    """Write a file made of the given lines under root, creating parent directories."""
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_size_limits_repository_within_limits() -> None:
    assert size_violations(REPO_ROOT) == ()


def test_size_limits_module_301_lines_rejected(tmp_path: Path) -> None:
    plant(tmp_path, "api/domain/long.py", ["X = 1"] * 301)
    assert size_violations(tmp_path) == ("api/domain/long.py: 301 lines > 300",)


def test_size_limits_module_300_lines_accepted(tmp_path: Path) -> None:
    plant(tmp_path, "api/domain/long.py", ["X = 1"] * 300)
    assert size_violations(tmp_path) == ()


def test_size_limits_exempt_module_accepted(tmp_path: Path) -> None:
    plant(tmp_path, "ml/schemas.py", ["X = 1"] * 301)
    assert size_violations(tmp_path) == ()


def test_size_limits_class_151_lines_rejected(tmp_path: Path) -> None:
    plant(tmp_path, "api/domain/big.py", ["class Big:", *["    a = 1"] * 150])
    assert size_violations(tmp_path) == ("api/domain/big.py:1: class Big has 151 lines > 150",)


def test_size_limits_class_150_lines_accepted(tmp_path: Path) -> None:
    plant(tmp_path, "api/domain/big.py", ["class Big:", *["    a = 1"] * 149])
    assert size_violations(tmp_path) == ()
