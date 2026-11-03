"""Versioned prompt files.

Changing a prompt means adding a new file (verdict_v2.md) and switching the name in code.
Every trace then records which wording produced it, and rolling back is a one-line change.
"""

from functools import cache
from pathlib import Path


@cache
def load(name: str) -> str:
    return (Path(__file__).parent / f"{name}.md").read_text(encoding="utf-8")
