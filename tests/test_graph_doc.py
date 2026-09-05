"""The committed diagram matches the code.

A diagram that drifts from the thing it documents is worse than no diagram --
it is confidently wrong, which is the failure mode this whole repo is about.
"""

from pathlib import Path

from scripts_graph import DOC, render


def test_diagram_is_current():
    assert DOC.exists(), "run: uv run python scripts_graph.py"
    assert DOC.read_text() == render(), (
        "docs/graph.md is stale. Regenerate it:\n"
        "    uv run python scripts_graph.py"
    )
