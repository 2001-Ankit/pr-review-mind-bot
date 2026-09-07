"""Guards against the class of bug that made v0.1.0 unusable from PyPI.

None of the previous tests imported the package the way an installed user
would, so a wheel that shipped the wrong top-level name and omitted its data
files passed CI cleanly.
"""

import importlib
import tomllib
from pathlib import Path

import pytest

import reviewmindbot

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MODULES = [
    "reviewmindbot.api",
    "reviewmindbot.cache",
    "reviewmindbot.cli",
    "reviewmindbot.config",
    "reviewmindbot.core.chunking",
    "reviewmindbot.core.diff_parser",
    "reviewmindbot.engine.aggregator",
    "reviewmindbot.engine.file_router",
    "reviewmindbot.engine.models",
    "reviewmindbot.engine.orchestrator",
    "reviewmindbot.engine.reviewer",
    "reviewmindbot.engine.test_generator",
    "reviewmindbot.errors",
    "reviewmindbot.integration.github",
    "reviewmindbot.integration.publisher",
    "reviewmindbot.llm.base",
    "reviewmindbot.llm.factory",
    "reviewmindbot.reporting.formatters",
    "reviewmindbot.usage",
]


@pytest.mark.parametrize("module", MODULES)
def test_every_module_imports(module):
    """A subpackage missing from the wheel shows up here, not in a bug report."""
    assert importlib.import_module(module) is not None


def test_no_top_level_app_package():
    """`app` is far too generic a name to install into site-packages."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app")


def test_bundled_example_diff_is_reachable():
    from reviewmindbot.examples import example_path

    path = example_path()

    assert path.is_file()
    assert path.read_text(encoding="utf-8").startswith("diff --git")


def test_entry_point_target_is_callable():
    from reviewmindbot.cli import main

    assert callable(main)


def test_version_is_consistent_with_pyproject():
    pyproject = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert pyproject["project"]["version"] == reviewmindbot.__version__


def test_declared_dependencies_cover_the_base_imports():
    """`requests` was used at runtime but never declared; it only worked by luck."""
    pyproject = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    declared = " ".join(pyproject["project"]["dependencies"])

    assert "requests" in declared
    assert "python-dotenv" in declared


def test_provider_sdks_are_optional_extras():
    """The base install must not pull in three vendors' clients."""
    pyproject = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    base = " ".join(pyproject["project"]["dependencies"])
    extras = pyproject["project"]["optional-dependencies"]

    assert "google-genai" not in base
    assert "openai" not in base
    assert "google-genai" in " ".join(extras["gemini"])
    assert "openai" in " ".join(extras["openai"])
