"""Bundled sample diffs, shipped as package data.

The README told users to run ``app/examples/simple_change.diff``, which did not
exist after ``pip install``. :func:`example_path` resolves it in both the source
tree and an installed wheel.
"""

from importlib import resources
from pathlib import Path


def example_path(name: str = "simple_change.diff") -> Path:
    return Path(str(resources.files(__package__).joinpath(name)))


__all__ = ["example_path"]
