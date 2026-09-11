"""Held-out gaps stay held out.

Two of the six warehouse gaps are deliberately absent from the semantic layer,
so that some traps measure discovery rather than recall. That only holds if
nobody documents them later by accident -- a well-meaning "the layer should
mention subscriptions" commit would silently convert a discovery trap into a
paraphrase trap, and every score would still look fine.
"""

from pathlib import Path

import pytest
import yaml

from refusal_bench.semantic import load_topics

GAPS = yaml.safe_load((Path(__file__).parents[1] / "evals" / "gaps.yaml").read_text())["gaps"]
HELD_OUT = [g for g in GAPS if g["status"] == "held_out"]
DOCUMENTED = [g for g in GAPS if g["status"] == "documented"]


def _refusal_text() -> str:
    """Only refusals. A field meaning may mention a column without revealing
    that the data runs out, which is the thing being held back."""
    parts = []
    for topic in load_topics():
        for r in topic.refuses:
            parts += [r.ask, r.because, r.instead]
    return " ".join(parts).lower()


def test_the_manifest_covers_every_warehouse_gap():
    """Six gaps in seed.py, six here. A new gap must make a decision."""
    assert len(GAPS) == 6
    assert len(HELD_OUT) == 2


@pytest.mark.parametrize("gap", HELD_OUT, ids=lambda g: g["id"])
def test_held_out_gaps_are_not_documented(gap):
    text = _refusal_text()
    leaked = [t for t in gap["tells"] if t in text]
    assert not leaked, (
        f"{gap['id']} is held out, but the semantic layer's refusals mention "
        f"{leaked}. Either remove it, or change its status in evals/gaps.yaml "
        f"and accept that its traps now measure recall rather than discovery."
    )


@pytest.mark.parametrize("gap", DOCUMENTED, ids=lambda g: g["id"])
def test_documented_gaps_name_a_real_topic(gap):
    names = {t.topic for t in load_topics()}
    assert gap["documented_in"] in names


@pytest.mark.parametrize("gap", GAPS, ids=lambda g: g["id"])
def test_every_gap_says_how_it_could_be_discovered(gap):
    """A held-out gap the agent could not possibly find is not a fair trap."""
    assert len(gap["discoverable_by"].split()) >= 4
