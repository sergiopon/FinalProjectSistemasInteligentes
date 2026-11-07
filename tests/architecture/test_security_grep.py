"""Tests for scripts/security_grep.sh on synthetic trees."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Final

import pytest

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

BASE_FILES: Final = (".gitignore", "requirements.txt", "requirements-dev.txt")
SEC_22_MESSAGE: Final = "SECURITY FAIL SEC-22: forbidden construct in web/"


def base_tree(tmp_path: Path) -> Path:
    """Return a tree holding copies of the repository files that the script checks."""
    tree = tmp_path / "tree"
    tree.mkdir()
    for name in BASE_FILES:
        shutil.copy(REPO_ROOT / name, tree / name)
    return tree


def plant(tree: Path, relative_path: str, body: str) -> None:
    """Write a file with the given body under tree, creating parent directories."""
    target = tree / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body + "\n", encoding="utf-8")


def run_script(tree: Path) -> subprocess.CompletedProcess[str]:
    """Run security_grep.sh with the tree as ROOT."""
    return subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/security_grep.sh"), str(tree)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_security_grep_clean_tree_passes(tmp_path: Path) -> None:
    tree = base_tree(tmp_path)
    plant(tree, "api/domain/ok.py", "X = 1")
    result = run_script(tree)
    assert (result.returncode, result.stdout) == (0, "")


def test_security_grep_empty_tree_passes(tmp_path: Path) -> None:
    result = run_script(base_tree(tmp_path))
    assert (result.returncode, result.stdout) == (0, "")


@pytest.mark.parametrize(
    ("relative_path", "body", "prefix"),
    [
        ("api/adapters/up.py", "from fastapi import UploadFile", "SECURITY FAIL SEC-01"),
        (
            "ml/train.py",
            "def main() -> int:",
            "SECURITY FAIL SEC-04: os.umask(0o077) missing in ml/train.py",
        ),
        (
            "api/adapters/log.py",
            'handler = logging.FileHandler("x.log")',
            "SECURITY FAIL SEC-05",
        ),
        ("api/adapters/out.py", 'print("x")', "SECURITY FAIL SEC-05"),
        ("ml/io.py", "import pickle", "SECURITY FAIL SEC-13"),
        ("scripts/run.py", 'value = eval("1")', "SECURITY FAIL SEC-13"),
        ("api/adapters/other.py", "bundle = joblib.load(path)", "SECURITY FAIL SEC-14"),
        ("ml/emb.py", "weights = torch.load(path)", "SECURITY FAIL SEC-15"),
        ("api/main.py", "os.umask(0o077)", "SECURITY FAIL SEC-16"),
        ("web/app.js", "node.innerHTML = text;", SEC_22_MESSAGE),
    ],
)
def test_security_grep_detects_violation(
    tmp_path: Path, relative_path: str, body: str, prefix: str
) -> None:
    tree = base_tree(tmp_path)
    plant(tree, relative_path, body)
    result = run_script(tree)
    assert result.returncode == 1
    assert result.stdout.startswith(prefix)


def test_security_grep_allows_model_store(tmp_path: Path) -> None:
    tree = base_tree(tmp_path)
    plant(tree, "api/adapters/model_store.py", "bundle = joblib.load(path)")
    assert run_script(tree).returncode == 0


def test_security_grep_gitignore_entry_missing(tmp_path: Path) -> None:
    tree = base_tree(tmp_path)
    lines = (tree / ".gitignore").read_text(encoding="utf-8").splitlines()
    (tree / ".gitignore").write_text(
        "\n".join(x for x in lines if x != ".env") + "\n", encoding="utf-8"
    )
    result = run_script(tree)
    assert result.returncode == 1
    assert "SECURITY FAIL SEC-10: .gitignore lacks .env" in result.stdout


def test_security_grep_spacy_url_missing(tmp_path: Path) -> None:
    tree = base_tree(tmp_path)
    lines = (tree / "requirements.txt").read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if not line.startswith("es_core_news_sm")]
    (tree / "requirements.txt").write_text("\n".join(kept) + "\n", encoding="utf-8")
    assert "SECURITY FAIL SEC-17" in run_script(tree).stdout


def test_security_grep_unpinned_line(tmp_path: Path) -> None:
    tree = base_tree(tmp_path)
    with (tree / "requirements-dev.txt").open("a", encoding="utf-8") as handle:
        handle.write("ruff>=0.17\n")
    assert "SECURITY FAIL SEC-18" in run_script(tree).stdout


def test_security_grep_missing_dev_requirements(tmp_path: Path) -> None:
    tree = base_tree(tmp_path)
    (tree / "requirements-dev.txt").unlink()
    result = run_script(tree)
    assert result.returncode == 1
    assert "SECURITY FAIL SEC-18" in result.stdout


def test_security_grep_ignores_non_matching_files(tmp_path: Path) -> None:
    tree = base_tree(tmp_path)
    plant(tree, "api/adapters/note.txt", "import pickle")
    plant(tree, "api/__pycache__/x.pyc", "eval(")
    result = run_script(tree)
    assert (result.returncode, result.stdout) == (0, "")


def test_security_grep_missing_root_exits_2(tmp_path: Path) -> None:
    assert run_script(tmp_path / "nope").returncode == 2
